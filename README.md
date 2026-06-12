# AI Research Paper Intelligence

A Flask-based web application that analyzes scientific research papers using Google's Gemini AI. Simply upload any research PDF to instantly generate structured summaries, technical breakdowns, interactive study flashcards, and access a contextual chat assistant.

---

## ✨ Features

*   **📄 PDF Text Extraction**: Securely parses text contents from uploaded academic PDFs using PyPDF2.
*   **🤖 AI-Generated Summaries**: Produces structured lists of key contributions, main takeaways, and abstract overviews.
*   **🔬 Technical Breakdowns**: Isolates paper methodology, experimental results, and limitations into separate, structured cards.
*   **🧠 3D Interactive Flashcards**: Generates 10 customizable study cards across sections (Abstract, Intro, Method, Results, Limitations) with a session-based mastery tracker.
*   **💬 AI Chat Assistant**: Offers an interactive contextual chatbot pre-loaded with smart prompts for direct Q&A about the paper.
*   **💾 Markdown Notes Export**: Lets you download the full structured summary and study flashcards as a clean markdown file for Obsidian or Notion.
*   **🎨 Premium Glassmorphic UI**: Designed with a high-fidelity dark mode palette, neon accents, and smooth hover micro-animations.

---

## 🛠️ Technologies Used

*   **Backend**: Python, Flask, PyPDF2 (PDF parsing)
*   **Frontend**: HTML5, Vanilla CSS3 (3D Card Transitions, Glassmorphic Design), JavaScript (ES6+ async requests)
*   **AI Model**: Google Gemini API (`gemini-2.0-flash`)
*   **Configuration**: python-dotenv (environment variables management)

---

## 🚀 How to Run

Follow these simple steps to run the application locally on your machine:

### 1. Set Up Virtual Environment (Recommended)
Navigate to the project directory and create a virtual environment:
```powershell
python -m venv venv
.\venv\Scripts\Activate
```

### 2. Install Dependencies
Install the required packages listed in the requirements file:
```bash
pip install -r requirements.txt
```

### 3. Configure Gemini API Key
Create a `.env` file in the root directory and add your keys:
```env
GEMINI_API_KEY=your_actual_gemini_api_key
FLASK_SECRET_KEY=some_secure_random_string
```
> Get a free API key from [Google AI Studio](https://aistudio.google.com/).

### 4. Run the Server
Launch the Flask development server:
```bash
python app.py
```

### 5. Open in Browser
Visit the application local address:
```text
http://127.0.0.1:5000
```

---

## 📸 Project Workflow

1.  **Upload Research Paper**: User uploads a scientific paper in PDF format.
2.  **Extract Text**: The backend extracts text lines and filters out unnecessary whitespace.
3.  **Gemini AI Analysis**: The text is sent to the Gemini model with a structured JSON schema prompt.
4.  **Generate Summary**: The AI model returns structured data, which is parsed and mapped.
5.  **Generate Flashcards**: Interactive 3D study cards are rendered based on paper sections.
6.  **Display Results**: Users can view data, export summaries to markdown, or chat with the paper.

---

## 📤 Git Repository Guidelines (What to Upload)

We have configured a `.gitignore` file to ensure sensitive keys and cache files are not pushed to GitHub:
*   **Files to upload/commit**: `app.py`, `requirements.txt`, `README.md`, `.gitignore`, `templates/`, `static/`
*   **DO NOT upload/commit**: `.env` (API Keys), `venv/` (Local environment), `uploads/` (User session text cache files)

---

## 🔒 Security & Privacy

*   Uploaded PDF files are parsed in memory and deleted from server storage immediately after extraction.
*   Parsed text contents are temporarily stored in `uploads/<session_id>.txt` only to power the contextual chat assistant, protecting document confidentiality.

---

## 👤 Author
Shrey Gamit   