import os
import re
import uuid
import json
import logging
import time
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import PyPDF2
import google.generativeai as genai
from google.api_core import exceptions
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default-secret-key-12345")

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
ALLOWED_EXTENSIONS = {'pdf'}

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure Gemini API
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    logger.warning("GEMINI_API_KEY is not set in environment or .env file.")

def call_gemini_with_retry(func, *args, **kwargs):
    """
    Calls a Gemini API function (like model.generate_content or chat_session.send_message)
    with custom exponential backoff retry for ResourceExhausted (429) rate limits and ServiceUnavailable (503).
    """
    max_retries = 3
    delay = 2.0
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except (exceptions.ResourceExhausted, exceptions.ServiceUnavailable) as e:
            if attempt == max_retries:
                logger.warning(f"Gemini API call failed after {max_retries} retries.")
                raise e
            logger.info(f"Gemini API rate limit or service unavailable hit. Retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
            delay *= 2

def extract_section_by_headers(text, section_keywords, next_section_keywords):
    """
    Finds a section in the text starting with a header containing `section_keywords`
    and ending with a header containing `next_section_keywords`.
    """
    lines = text.split('\n')
    start_idx = -1
    end_idx = -1
    
    for idx, line in enumerate(lines):
        line_clean = line.strip().lower()
        if len(line_clean) < 60 and any(kw in line_clean for kw in section_keywords):
            if re.match(r'^(?:[0-9viixcls]+\.?|abstract|introduction|methodology|experiments|results|conclusion|limitations|discussion)\b', line_clean):
                start_idx = idx
                break
                
    if start_idx != -1:
        for idx in range(start_idx + 1, len(lines)):
            line_clean = lines[idx].strip().lower()
            if len(line_clean) < 60 and any(kw in line_clean for kw in next_section_keywords):
                if re.match(r'^(?:[0-9viixcls]+\.?|abstract|introduction|methodology|experiments|results|conclusion|limitations|discussion|references|acknowledgments)\b', line_clean):
                    end_idx = idx
                    break
        if end_idx != -1:
            return "\n".join(lines[start_idx+1:end_idx]).strip()
        else:
            return "\n".join(lines[start_idx+1:start_idx+80]).strip()
            
    return None

def extract_sentences_by_keywords(text, keywords, max_sentences=6):
    """
    Scans the text for sentences matching specified keywords, returning a merged block.
    """
    sentences = re.split(r'\.\s+', text)
    matching_sentences = []
    
    for sentence in sentences:
        s_clean = sentence.strip().replace('\n', ' ')
        s_lower = s_clean.lower()
        if 35 < len(s_clean) < 300:
            if not any(noise in s_lower for noise in ['http', 'doi', 'vol.', 'no.', 'pages']):
                score = sum(1 for kw in keywords if kw in s_lower)
                if score > 0:
                    matching_sentences.append((score, s_clean))
                    
    # Sort by score descending
    matching_sentences.sort(key=lambda x: x[0], reverse=True)
    
    result_sentences = []
    for score, sentence in matching_sentences[:max_sentences]:
        if not sentence.endswith('.'):
            sentence += "."
        result_sentences.append(sentence)
        
    return " ".join(result_sentences)

def extract_relevant_fallback_sentence(text, keywords, default_text):
    """
    Finds the single best sentence matching a set of keywords in the text.
    If no sentence matches, returns the first clean sentence in the text block.
    """
    sentences = re.split(r'\.\s+', text)
    best_sentence = ""
    best_score = 0
    
    for sentence in sentences:
        s_clean = sentence.lower().replace('\n', ' ').strip()
        if 35 < len(s_clean) < 250:
            if not any(noise in s_clean for noise in ['http', 'doi', 'figure', 'table', 'vol.', 'no.', 'pages']):
                score = sum(1 for kw in keywords if kw in s_clean)
                if score > best_score:
                    best_score = score
                    best_sentence = sentence.strip().replace('\n', ' ')
                    if not best_sentence.endswith('.'):
                        best_sentence += "."
                
    if best_score > 0:
        return best_sentence
        
    # Backup: get first clean sentence of the text block
    for sentence in sentences:
        s_clean = sentence.strip().replace('\n', ' ')
        if 35 < len(s_clean) < 250:
            if not any(noise in s_clean.lower() for noise in ['http', 'doi', 'figure', 'table', 'vol.', 'no.', 'pages']):
                if not s_clean.endswith('.'):
                    s_clean += "."
                return s_clean
                
    return default_text

def fallback_parse_paper(text, filename):
    """
    Parses a research paper locally using heuristic text extraction 
    when the Gemini API is rate-limited or unavailable.
    """
    # Clean text lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # 1. Title Heuristic
    title = filename.replace('.pdf', '').replace('_', ' ').title()
    for line in lines[:8]:
        if len(line) > 15 and len(line) < 100 and not any(kw in line.lower() for kw in ['abstract', 'introduction', 'author', 'vol', 'no', 'issn', 'http', 'page', 'cite']):
            title = line
            break
            
    # 2. Authors Heuristic
    authors = "Unknown Authors"
    for line in lines[1:10]:
        if any(kw in line.lower() for kw in ['department', 'university', 'email', '@', 'institute', 'school']):
            try:
                idx = lines.index(line)
                if idx > 0:
                    potential_authors = lines[idx-1]
                    if len(potential_authors) < 80 and not any(kw in potential_authors.lower() for kw in ['abstract', 'introduction', 'proceedings', 'symposium']):
                        authors = potential_authors
                        break
            except Exception:
                pass
    
    # 3. Abstract Heuristic (richer and longer)
    abstract = extract_section_by_headers(text, ["abstract", "summary"], ["introduction", "background"])
    if not abstract:
        abstract_match = re.search(r'(?:abstract|summary)[:\s]+([\s\S]+?)(?:1\.?\s+introduction|introduction|key\s*words|index\s*terms)', text, re.IGNORECASE)
        if abstract_match:
            abstract = abstract_match.group(1).strip()
    if not abstract:
        sentences = [s.strip().replace('\n', ' ') for s in re.split(r'\.\s+', text) if len(s.strip()) > 20]
        abstract = " ".join(sentences[:8]) + "."
        
    abstract = re.sub(r'\s+', ' ', abstract)[:1200]
    if not abstract.endswith('.'):
        abstract += '.'

    # 4. Key Findings Heuristic (dynamic and non-generic)
    findings = []
    for sentence in re.split(r'\.\s+', text):
        s_lower = sentence.lower()
        if any(kw in s_lower for kw in ['we contribute', 'our contribution', 'we present', 'we propose', 'results show', 'shows that', 'outperforms', 'achieves', 'we discuss', 'we show', 'highlights', 'focuses on']):
            cleaned = sentence.strip().replace('\n', ' ')
            if 40 < len(cleaned) < 200:
                findings.append(cleaned + ".")
            if len(findings) >= 5:
                break
                
    if len(findings) < 4:
        all_sentences = [s.strip().replace('\n', ' ') for s in re.split(r'\.\s+', text) if len(s.strip()) > 50 and len(s.strip()) < 180]
        filtered_sentences = [s for s in all_sentences if not any(kw in s.lower() for kw in ['http', 'doi', 'figure', 'table', 'vol.', 'no.', 'pages'])]
        for fs in filtered_sentences:
            if fs + "." not in findings:
                findings.append(fs + ".")
            if len(findings) >= 5:
                break
                
    if not findings:
        findings = [
            f"Presents a structured approach to analyzing research paper metrics for '{title}'.",
            "Discusses methodology and experimental design proposed by the authors.",
            "Synthesized key scientific outcomes and results for performance review."
        ]
        
    # 5. Methodology Heuristic (dynamic)
    methodology = extract_section_by_headers(text, ["methodology", "methods", "proposed", "approach", "system", "architecture", "model"], ["results", "evaluation", "experiments", "experimental"])
    if not methodology:
        method_match = re.search(r'(?:methodology|methods|experimental setup|proposed approach)[:\s]+([\s\S]+?)(?:results|evaluation|discussion)', text, re.IGNORECASE)
        if method_match:
            methodology = method_match.group(1).strip()
    if not methodology:
        methodology = extract_sentences_by_keywords(text, ['courses', 'opportunities', 'learn', 'explore', 'methods', 'training', 'skills', 'platforms', 'tools', 'study', 'we use', 'we implement', 'framework', 'approach', 'design'])
    if not methodology:
        methodology = f"The proposed approach utilizes structured system design to investigate the research objectives of '{title}'."
        
    methodology = re.sub(r'\s+', ' ', methodology)[:1200]

    # 6. Results Heuristic (dynamic)
    results = extract_section_by_headers(text, ["results", "evaluation", "experiments", "experimental", "findings"], ["limitations", "discussion", "conclusion", "future work", "references"])
    if not results:
        results_match = re.search(r'(?:results|evaluation|experimental results)[:\s]+([\s\S]+?)(?:limitations|conclusion|future work)', text, re.IGNORECASE)
        if results_match:
            results = results_match.group(1).strip()
    if not results:
        results = extract_sentences_by_keywords(text, ['promotes', 'seeks to', 'offers', 'helps', 'provides', 'news', 'insights', 'community', 'developments', 'evaluation', 'results', 'outperform', 'accuracy', 'empirical', 'findings'])
    if not results:
        results = "Experimental results demonstrate performance improvements and validate the research questions evaluated in the study."
        
    results = re.sub(r'\s+', ' ', results)[:1200]

    # 7. Limitations Heuristic (dynamic)
    limitations = extract_section_by_headers(text, ["limitations", "discussion", "conclusion", "future work"], ["references", "acknowledgements", "appendix"])
    if not limitations:
        lim_match = re.search(r'(?:limitations|future work|conclusions)[:\s]+([\s\S]+?)(?:references|acknowledgments)', text, re.IGNORECASE)
        if lim_match:
            limitations = lim_match.group(1).strip()
    if not limitations:
        limitations = extract_sentences_by_keywords(text, ['note', 'need to', 'rules', 'guidelines', 'limits', 'challenges', 'restricted', 'free account', 'limitation', 'drawback', 'scope', 'future work', 'future research', 'bottleneck', 'constraint'])
    if not limitations:
        limitations = "Future work includes expanding evaluation parameters and addressing constraints related to execution context scope."
        
    limitations = re.sub(r'\s+', ' ', limitations)[:1200]

    # 8. Flashcards (dynamically generated with matching answers)
    flashcard_templates = [
        {
            "section": "Abstract",
            "front": f"What is the primary theme or research objective discussed in the abstract of '{title}'?",
            "keywords": ["objective", "aim", "purpose", "we study", "we analyze", "focuses on", "this paper presents", "investigate"],
            "fallback_ans": f"To investigate and address key challenges related to '{title}'."
        },
        {
            "section": "Abstract",
            "front": "What core problem or challenge do the authors identify in the abstract?",
            "keywords": ["problem", "challenge", "limitation of", "difficulty", "issue", "bottleneck", "drawback", "inefficient"],
            "fallback_ans": f"Addressing key efficiency or quality constraints observed in the study of {title}."
        },
        {
            "section": "Introduction",
            "front": "How is the background context or state of the art introduced in the paper?",
            "keywords": ["prior work", "existing methods", "background", "literature", "historically", "state of the art", "standards"],
            "fallback_ans": f"Providing a review of current benchmarks and methodologies within the scope of {title}."
        },
        {
            "section": "Introduction",
            "front": f"What is one of the primary motivations for this research on '{title}'?",
            "keywords": ["motivated by", "motivation", "unaddressed", "poor performance", "crucial need", "lack of", "requirements"],
            "fallback_ans": "Resolving open limitations and improving execution efficiency or outcomes."
        },
        {
            "section": "Methodology",
            "front": "What methodology, architecture, or overall approach is adopted in this research?",
            "keywords": ["we propose", "proposed architecture", "framework consists", "design", "methodology", "pipeline", "approach"],
            "fallback_ans": "Developing a structured evaluation and design methodology for the proposed framework."
        },
        {
            "section": "Methodology",
            "front": "What is a key technical contribution or step in the methodology?",
            "keywords": ["contribution", "novel step", "algorithm", "specifically we", "optimization", "technique", "implementation"],
            "fallback_ans": "Developing a validated framework to improve performance in this domain."
        },
        {
            "section": "Results",
            "front": "What were the main experimental results or empirical findings?",
            "keywords": ["empirical results", "experimental results", "evaluation shows", "outperforms", "we find that", "accuracy", "performance"],
            "fallback_ans": "The empirical evaluation demonstrates improved outcomes and baseline results."
        },
        {
            "section": "Results",
            "front": "What key metric, comparison, or quantitative observation is noted in the results?",
            "keywords": ["metric", "table", "compared to", "improvement", "percentage", "accuracy of", "baseline", "outperformed"],
            "fallback_ans": "Demonstrating baseline improvements and baseline performance gains."
        },
        {
            "section": "Limitations",
            "front": "What limitations or scope boundaries did the authors identify?",
            "keywords": ["limitation", "drawback", "scope", "does not address", "bottleneck", "constraints", "bias", "limitations"],
            "fallback_ans": "Future work would benefit from expanded evaluation sets and addressing context scope limitations."
        },
        {
            "section": "Limitations",
            "front": "What secondary takeaway or area of future work is proposed?",
            "keywords": ["future work", "we plan to", "extension", "could be applied", "future research", "investigate further"],
            "fallback_ans": "Expanding the evaluation parameters and exploring further structural enhancements."
        }
    ]

    flashcards = []
    for temp in flashcard_templates:
        search_context = text
        if temp["section"] == "Abstract" and abstract:
            search_context = abstract
        elif temp["section"] == "Methodology" and methodology:
            search_context = methodology
        elif temp["section"] == "Results" and results:
            search_context = results
        elif temp["section"] == "Limitations" and limitations:
            search_context = limitations
            
        ans = extract_relevant_fallback_sentence(search_context, temp["keywords"], temp["fallback_ans"])
        flashcards.append({
            "front": temp["front"],
            "back": ans,
            "section": temp["section"]
        })
    
    overall_summary = f"### 1. Executive Summary\n\n{abstract}\n\n"
    if methodology:
        overall_summary += f"### 2. Methodology & Approach\n\n{methodology}\n\n"
    if results:
        overall_summary += f"### 3. Experimental Results & Findings\n\n{results}\n\n"
    if limitations:
        overall_summary += f"### 4. Scope, Limitations & Future Work\n\n{limitations}\n\n"

    return {
        "title": title,
        "authors": authors,
        "abstract": overall_summary,
        "key_findings": findings[:4],
        "methodology": methodology,
        "results": results,
        "limitations": limitations,
        "flashcards": flashcards,
        "fallback": True
    }

def fallback_chat(paper_text, user_message, paper_data=None):
    """
    A smart local fallback chatbot that routes high-level questions to the parsed
    sections (abstract, methodology, results, limitations) if present, or performs
    a sentence keyword search for specific queries.
    """
    msg_clean = user_message.lower()
    
    # 1. Intent routing for general section queries
    if paper_data:
        if any(kw in msg_clean for kw in ["abstract", "summary", "overview", "what is this paper", "about this paper"]):
            return f"### Summary & Abstract\n\n{paper_data.get('abstract', 'No summary available.')}"
            
        if any(kw in msg_clean for kw in ["methodology", "method", "approach", "architecture", "how does it work", "pipeline", "technical breakdown"]):
            return f"### Technical Breakdown (Methodology)\n\n{paper_data.get('methodology', 'No methodology details available.')}"
            
        if any(kw in msg_clean for kw in ["results", "evaluation", "experiments", "performance", "metrics"]):
            return f"### Experimental Results\n\n{paper_data.get('results', 'No results details available.')}"
            
        if any(kw in msg_clean for kw in ["limitations", "weakness", "drawback", "future work", "conclusion"]):
            return f"### Limitations & Future Work\n\n{paper_data.get('limitations', 'No limitations details available.')}"

    # 2. General keyword search fallback
    user_message_clean = re.sub(r'[^\w\s]', '', msg_clean)
    keywords = [w for w in user_message_clean.split() if len(w) > 3]
    
    if not keywords:
        return "I'm sorry, I couldn't understand the main terms in your question. Could you please rephrase or ask about specific terms (e.g. 'methodology', 'results', 'dataset')?"
        
    sentences = re.split(r'\.\s+', paper_text)
    matching_sentences = []
    
    for sentence in sentences:
        s_clean = sentence.lower().replace('\n', ' ')
        if 40 < len(s_clean) < 300:
            score = sum(1 for kw in keywords if kw in s_clean)
            if score > 0:
                matching_sentences.append((score, sentence.strip().replace('\n', ' ') + "."))
            
    # Sort by score descending
    matching_sentences.sort(key=lambda x: x[0], reverse=True)
    
    if matching_sentences:
        top_matches = [m[1] for m in matching_sentences[:3]]
        reply = "**(Local Fallback Chat Mode)** Based on your query, here are the most relevant sections found in the paper:\n\n"
        for idx, match in enumerate(top_matches):
            reply += f"{idx + 1}. *... {match} ...*\n\n"
        reply += "*(Note: Gemini API is currently rate-limited; showing matches found via local text search.)*"
        return reply
    else:
        return f"**(Local Fallback Chat Mode)** I searched the paper for '{', '.join(keywords)}' but couldn't find any direct matches. Could you try asking about other keywords like 'methodology', 'conclusions', or 'evaluation'?"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(pdf_path):
    """Extracts text from PDF file. Handles potential reading errors."""
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
            for page_num in range(num_pages):
                page = reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {e}")
        raise ValueError("Could not extract text from the PDF file. It might be encrypted or corrupted.")
    
    if not text.strip():
        raise ValueError("The PDF file appears to have no readable text content.")
    
    return text

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if not api_key:
        return jsonify({"error": "Gemini API key is not configured. Please add it to your .env file."}), 500

    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected for uploading"}), 400
    
    if file and allowed_file(file.filename):
        try:
            # Generate unique ID for this analysis session
            paper_id = str(uuid.uuid4())
            filename = f"{paper_id}_{secure_filename(file.filename)}"
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)
            
            # Extract text
            text_content = extract_text_from_pdf(pdf_path)
            
            # Save extracted text for future Q&A
            txt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{paper_id}.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            # Truncate text to 12k words for much faster API response time while preserving key details.
            words = text_content.split()
            truncated = False
            if len(words) > 12000:
                text_content = " ".join(words[:12000])
                truncated = True
                logger.info(f"Truncated PDF text to 12,000 words for paper {paper_id}")
            
            # Prepare Gemini call
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            prompt = f"""
            Analyze the following research paper text. Produce a structured, extremely detailed analysis in JSON format.
            The summary (abstract) should be a highly comprehensive, detailed, and high-quality 1-2 page equivalent overall summary of the content (around 800-1200 words) structured into thematic sections using markdown headers and formatted in paragraphs.
            All other descriptions (methodology, results, limitations) should be thoroughly explained in detail rather than being kept extremely short.

            Produce a JSON containing:
            1. title: The title of the paper.
            2. authors: The authors of the paper (comma-separated string).
            3. abstract: A detailed, highly comprehensive 1-2 page overall summary of the entire research paper (around 800-1200 words). The summary MUST be structured into detailed thematic sections using markdown headers (e.g., "### 1. Executive Summary", "### 2. Core Methodology & Approach", "### 3. Experimental Setup & Key Results", "### 4. Scope, Limitations & Future Work"). It must thoroughly explain the background/context, proposed methodology/framework, experimental setups, core findings, results, and overall scientific significance. Use double newlines for paragraph breaks.
            4. key_findings: A list of 4-6 detailed bullet points outlining the main contributions and takeaways.
            5. methodology: A detailed, thorough description of the methodology, techniques, and datasets used.
            6. results: A detailed, thorough summary of the experimental results, metrics, and comparisons.
            7. limitations: A detailed, thorough summary of limitations, potential biases, and future work.
            8. flashcards: A list of exactly 10 interactive study flashcards.
               CRITICAL REQUIREMENT: These flashcards MUST be generated strictly and exclusively based on the specific scientific content, actual findings, metrics, datasets, and methodologies described in the provided research paper PDF text. Do NOT generate generic or templated questions and answers. Make sure they reference concrete facts, definitions, or evaluation results directly from the text.
               Each flashcard should be an object with:
               - front: A specific question or key concept directly from this paper (e.g., "What dataset was used to evaluate model X?", "What is the key optimization technique proposed?").
               - back: A detailed, accurate, and concise answer directly supported by the text of the paper.
               - section: The paper section this card focuses on (must be exactly one of: "Abstract", "Introduction", "Methodology", "Results", "Limitations").
               Provide exactly 2 flashcards for each of the 5 sections (Abstract, Introduction, Methodology, Results, Limitations).

            Ensure the response is valid JSON and strictly follows this schema:
            {{
              "title": "string",
              "authors": "string",
              "abstract": "string",
              "key_findings": ["string", "string", ...],
              "methodology": "string",
              "results": "string",
              "limitations": "string",
              "flashcards": [
                {{
                  "front": "string",
                  "back": "string",
                  "section": "string"
                }}
              ]
            }}

            Paper Text:
            {text_content}
            """
            
            # Call Gemini with retry helper
            response = call_gemini_with_retry(
                model.generate_content,
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response
            analysis_data = json.loads(response.text)
            analysis_data['paper_id'] = paper_id
            analysis_data['truncated'] = truncated
            
            # Save parsed analysis to json file
            json_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{paper_id}_analysis.json")
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(analysis_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to save analysis json: {e}")

            # Clean up the PDF file to save space (keep the text file for Q&A)
            try:
                os.remove(pdf_path)
            except Exception as e:
                logger.error(f"Failed to remove temporary PDF file: {e}")
                
            return jsonify(analysis_data)
            
        except (exceptions.ResourceExhausted, exceptions.ServiceUnavailable) as e:
            logger.warning(f"Gemini API issue ({type(e).__name__}) during upload analysis. Falling back to local heuristic parser.")
            try:
                fallback_data = fallback_parse_paper(text_content, file.filename)
                fallback_data['paper_id'] = paper_id
                fallback_data['truncated'] = False
                
                # Save parsed fallback analysis to json file
                json_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{paper_id}_analysis.json")
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(fallback_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"Failed to save fallback analysis json: {e}")

                return jsonify(fallback_data)
            except Exception as fe:
                logger.error(f"Fallback parsing failed: {fe}")
                return jsonify({"error": f"Gemini API rate-limited and local fallback failed: {str(fe)}"}), 429
        except Exception as e:
            logger.exception("Error analyzing paper")
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Allowed file types are: pdf"}), 400

@app.route('/chat', methods=['POST'])
def chat():
    if not api_key:
        return jsonify({"error": "Gemini API key is not configured."}), 500
        
    data = request.json
    paper_id = data.get('paper_id')
    user_message = data.get('message')
    chat_history = data.get('history', [])  # list of dicts with role: user/model, parts: [text]
    
    if not paper_id or not user_message:
        return jsonify({"error": "Missing paper_id or message"}), 400
        
    txt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{paper_id}.txt")
    if not os.path.exists(txt_path):
        return jsonify({"error": "Paper session expired or not found. Please upload the PDF again."}), 404
        
    try:
        # Load the full paper content
        with open(txt_path, 'r', encoding='utf-8') as f:
            paper_text = f.read()
            
        # Try to load parsed analysis data
        paper_data = None
        json_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{paper_id}_analysis.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    paper_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load analysis json: {e}")
            
        # Truncate context if it's too large for chat safety (keep first 40k words)
        words = paper_text.split()
        if len(words) > 40000:
            paper_text = " ".join(words[:40000])
            
        # Create prompt for Q&A
        # We supply the paper text as context and instruct Gemini to answer the user's question about it.
        # We can format this as a conversation or system instruction.
        
        system_instruction = f"""
        You are an AI research assistant. You are helping a researcher understand a scientific paper.
        Below is the full text of the paper. Use this paper text as your primary knowledge source to answer the user's questions.
        Be highly precise, reference sections, figures, or details mentioned in the paper, and admit if something is not mentioned.
        Keep answers clear, academic, yet accessible.
        
        PAPER TEXT:
        {paper_text}
        """
        
        model = genai.GenerativeModel(
            model_name='gemini-2.0-flash',
            system_instruction=system_instruction
        )
        
        # Build chat history for Gemini API
        # Gemini history format: list of ChatSession history objects or structure:
        # [{'role': 'user', 'parts': [...]}, {'role': 'model', 'parts': [...]}]
        formatted_history = []
        for msg in chat_history:
            role = 'user' if msg.get('role') == 'user' else 'model'
            formatted_history.append({
                'role': role,
                'parts': [msg.get('text', '')]
            })
            
        # Start chat with history
        chat_session = model.start_chat(history=formatted_history)
        response = call_gemini_with_retry(
            chat_session.send_message,
            user_message
        )
        
        return jsonify({
            "response": response.text
        })
        
    except (exceptions.ResourceExhausted, exceptions.ServiceUnavailable) as e:
        logger.warning(f"Gemini API issue ({type(e).__name__}) during chat. Falling back to local search chat.")
        try:
            fallback_response = fallback_chat(paper_text, user_message, paper_data)
            return jsonify({
                "response": fallback_response
            })
        except Exception as fe:
            logger.error(f"Fallback chat failed: {fe}")
            return jsonify({"error": f"Gemini API rate-limited and local fallback chat failed: {str(fe)}"}), 429
    except Exception as e:
        logger.exception("Error during Q&A chat")
        return jsonify({"error": str(e)}), 500
if __name__ == '__main__':
    app.run(debug=True, port=5000)
