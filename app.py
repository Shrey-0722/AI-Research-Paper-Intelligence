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

def fallback_parse_paper(text, filename):
    """
    Parses a research paper locally using heuristic text extraction 
    when the Gemini API is rate-limited or unavailable.
    """
    # Clean text lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # 1. Title Heuristic
    title = filename.replace('.pdf', '').replace('_', ' ').title()
    # Try to find a better title in the first few lines
    for line in lines[:8]:
        if len(line) > 15 and len(line) < 100 and not any(kw in line.lower() for kw in ['abstract', 'introduction', 'author', 'vol', 'no', 'issn', 'http', 'page', 'cite']):
            title = line
            break
            
    # 2. Authors Heuristic
    authors = "Unknown Authors"
    for line in lines[1:10]:
        if any(kw in line.lower() for kw in ['department', 'university', 'email', '@', 'institute', 'school']):
            # Usually authors are in the lines before this
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
    abstract = "Abstract not found."
    abstract_match = re.search(r'(?:abstract|summary)[:\s]+([\s\S]+?)(?:1\.?\s+introduction|introduction|key\s*words|index\s*terms)', text, re.IGNORECASE)
    if abstract_match:
        abstract_raw = abstract_match.group(1).strip()
        sentences = [s.strip().replace('\n', ' ') for s in re.split(r'\.\s+', abstract_raw) if len(s.strip()) > 15]
        abstract = ". ".join(sentences[:5]) + "."
    else:
        # Fallback to first few sentences
        sentences = [s.strip().replace('\n', ' ') for s in re.split(r'\.\s+', text) if len(s.strip()) > 25]
        if len(sentences) > 0:
            abstract = ". ".join(sentences[:5]) + "."
        
    # 4. Key Findings Heuristic (dynamic and non-generic)
    findings = []
    # Search for sentences with contribution keywords first
    for sentence in re.split(r'\.\s+', text):
        s_lower = sentence.lower()
        if any(kw in s_lower for kw in ['we contribute', 'our contribution', 'we present', 'we propose', 'results show', 'shows that', 'outperforms', 'achieves', 'we discuss', 'we show', 'highlights', 'focuses on']):
            cleaned = sentence.strip().replace('\n', ' ')
            if 40 < len(cleaned) < 200:
                findings.append(cleaned + ".")
            if len(findings) >= 5:
                break
                
    # If we still don't have enough, pull informative sentences from the document
    if len(findings) < 4:
        all_sentences = [s.strip().replace('\n', ' ') for s in re.split(r'\.\s+', text) if len(s.strip()) > 50 and len(s.strip()) < 180]
        # filter out generic headings or citations
        filtered_sentences = [s for s in all_sentences if not any(kw in s.lower() for kw in ['http', 'doi', 'figure', 'table', 'vol.', 'no.', 'pages'])]
        for fs in filtered_sentences:
            if fs + "." not in findings:
                findings.append(fs + ".")
            if len(findings) >= 5:
                break
                
    # Ultimate fallback if text is extremely short
    if not findings:
        findings = [
            "Analyzed the uploaded text content and extracted main talking points.",
            "Discussed core concepts and topics presented by the author.",
            "Synthesized key highlights for further review and study."
        ]
        
    # 5. Methodology Heuristic (dynamic)
    methodology = ""
    method_match = re.search(r'(?:methodology|methods|experimental setup|proposed approach)[:\s]+([\s\S]+?)(?:results|evaluation|discussion)', text, re.IGNORECASE)
    if method_match:
        method_text = method_match.group(1).strip()
        sentences = re.split(r'\.\s+', method_text)
        methodology = ". ".join([s.strip().replace('\n', ' ') for s in sentences[:3]]) + "."
    else:
        # Search for methodology / action keywords
        method_sentences = []
        for sentence in re.split(r'\.\s+', text):
            s_lower = sentence.lower()
            if any(kw in s_lower for kw in ['we design', 'we implement', 'the method consists', 'our architecture', 'framework', 'using', 'first', 'then', 'process', 'step', 'strategy']):
                cleaned = sentence.strip().replace('\n', ' ')
                if 50 < len(cleaned) < 200:
                    method_sentences.append(cleaned + ".")
                if len(method_sentences) >= 2:
                    break
        if method_sentences:
            methodology = " ".join(method_sentences)
        else:
            methodology = "The proposed approach utilizes structured text analysis and contextual parsing of the document content to organize the author's arguments."

    # 6. Results Heuristic (dynamic)
    results = ""
    results_match = re.search(r'(?:results|evaluation|experimental results)[:\s]+([\s\S]+?)(?:limitations|conclusion|future work)', text, re.IGNORECASE)
    if results_match:
        results_text = results_match.group(1).strip()
        sentences = re.split(r'\.\s+', results_text)
        results = ". ".join([s.strip().replace('\n', ' ') for s in sentences[:3]]) + "."
    else:
        results_sentences = []
        for sentence in re.split(r'\.\s+', text):
            s_lower = sentence.lower()
            if any(kw in s_lower for kw in ['experiment results', 'achieved an accuracy', 'outperformed', 'table', 'figure show', 'empirical evaluation', 'show that', 'we found', 'demonstrates', 'observed']):
                cleaned = sentence.strip().replace('\n', ' ')
                if 50 < len(cleaned) < 200:
                    results_sentences.append(cleaned + ".")
                if len(results_sentences) >= 2:
                    break
        if results_sentences:
            results = " ".join(results_sentences)
        else:
            results = "Analysis of the document indicates structured support for the core findings and thematic arguments presented by the author."

    # 7. Limitations Heuristic (dynamic)
    limitations = ""
    lim_match = re.search(r'(?:limitations|future work|conclusions)[:\s]+([\s\S]+?)(?:references|acknowledgments)', text, re.IGNORECASE)
    if lim_match:
        lim_text = lim_match.group(1).strip()
        sentences = re.split(r'\.\s+', lim_text)
        limitations = ". ".join([s.strip().replace('\n', ' ') for s in sentences[:3]]) + "."
    else:
        lim_sentences = []
        for sentence in re.split(r'\.\s+', text):
            s_lower = sentence.lower()
            if any(kw in s_lower for kw in ['limitation', 'future work', 'drawback', 'scope of', 'we hope to', 'challenge', 'constraint', 'difficult to']):
                cleaned = sentence.strip().replace('\n', ' ')
                if 50 < len(cleaned) < 200:
                    lim_sentences.append(cleaned + ".")
                if len(lim_sentences) >= 2:
                    break
        if lim_sentences:
            limitations = " ".join(lim_sentences)
        else:
            limitations = "Future work would benefit from expanded evaluation sets, addressing constraints related to domain specificity and context scope."

    # 8. Flashcards (updated with dynamic metadata)
    flashcards = [
        {
            "front": "What is the primary objective of this research paper?",
            "back": f"To investigate and address key challenges related to '{title}'.",
            "section": "Abstract"
        },
        {
            "front": "What methodology or approach did the authors adopt?",
            "back": methodology[:180] + "..." if len(methodology) > 180 else methodology,
            "section": "Methodology"
        },
        {
            "front": "What were the main experimental results or findings?",
            "back": results[:180] + "..." if len(results) > 180 else results,
            "section": "Results"
        },
        {
            "front": "What limitations or areas of future work did the authors highlight?",
            "back": limitations[:180] + "..." if len(limitations) > 180 else limitations,
            "section": "Limitations"
        },
        {
            "front": "What is the core contribution of this work?",
            "back": findings[0] if len(findings) > 0 else "Developing a validated framework to improve performance in this domain.",
            "section": "Methodology"
        },
        {
            "front": "What is the overarching theme described in the abstract?",
            "back": abstract[:180] + "..." if len(abstract) > 180 else abstract,
            "section": "Abstract"
        },
        {
            "front": "What key problem is this research trying to solve?",
            "back": f"Resolving open limitations and improving execution efficiency or outcomes in the domain of {title}.",
            "section": "Introduction"
        },
        {
            "front": "Which specific area of study or domain does this paper target?",
            "back": f"Scientific research and applications relating to {title}.",
            "section": "Introduction"
        },
        {
            "front": "Why are the experimental findings in this paper significant?",
            "back": f"They provide empirical evidence and baseline comparisons supporting the proposed method's efficiency.",
            "section": "Results"
        },
        {
            "front": "What is a secondary contribution or takeaway highlighted in the study?",
            "back": findings[1] if len(findings) > 1 else "Establishing structured experimental benchmarks for future research.",
            "section": "Limitations"
        }
    ]
    
    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "key_findings": findings[:4],
        "methodology": methodology,
        "results": results,
        "limitations": limitations,
        "flashcards": flashcards,
        "fallback": True
    }

def fallback_chat(paper_text, user_message):
    """
    A smart local fallback chatbot that searches the paper for keywords 
    matching the user's message and returns the context.
    """
    user_message_clean = re.sub(r'[^\w\s]', '', user_message.lower())
    keywords = [w for w in user_message_clean.split() if len(w) > 3]
    
    if not keywords:
        return "I'm sorry, I couldn't understand the main terms in your question. Could you please rephrase or ask about specific terms (e.g. 'methodology', 'results', 'dataset')?"
        
    sentences = re.split(r'\.\s+', paper_text)
    matching_sentences = []
    
    for sentence in sentences:
        s_clean = sentence.lower().replace('\n', ' ')
        score = sum(1 for kw in keywords if kw in s_clean)
        if score > 0:
            matching_sentences.append((score, sentence.strip().replace('\n', ' ') + "."))
            
    # Sort by score descending
    matching_sentences.sort(key=lambda x: x[0], reverse=True)
    
    if matching_sentences:
        # Take the top 3 matches
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
            Analyze the following research paper text. Produce a structured analysis in JSON format.
            CRITICAL FOR SPEED: Keep all text explanations, methodologies, and results extremely concise, crisp, and limited to 1-3 sentences maximum.
 
            Produce a JSON containing:
            1. title: The title of the paper.
            2. authors: The authors of the paper (comma-separated string).
            3. abstract: A very brief summary of the paper.
            4. key_findings: A list of 3-4 bullet points of the main contributions.
            5. methodology: A 1-2 sentence description of the methodology.
            6. results: A 1-2 sentence summary of the experimental results.
            7. limitations: A 1-2 sentence summary of limitations.
            8. flashcards: A list of exactly 10 interactive study flashcards. Each flashcard should be an object with:
               - front: A question or key concept.
               - back: The answer or explanation.
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
            fallback_response = fallback_chat(paper_text, user_message)
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
