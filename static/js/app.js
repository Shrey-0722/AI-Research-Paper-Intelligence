document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const uploadSection = document.getElementById('upload-section');
    const loadingSection = document.getElementById('loading-section');
    const dashboardSection = document.getElementById('dashboard-section');

    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const filePreviewContainer = document.getElementById('file-preview-container');
    const previewFilename = document.getElementById('preview-filename');
    const previewFilesize = document.getElementById('preview-filesize');
    const btnRemoveFile = document.getElementById('btn-remove-file');
    const btnAnalyze = document.getElementById('btn-analyze');
    const btnNewUpload = document.getElementById('btn-new-upload');

    // Steps
    const step1 = document.getElementById('step-1');
    const step2 = document.getElementById('step-2');
    const step3 = document.getElementById('step-3');

    // Tab Navigation
    const navItems = document.querySelectorAll('.nav-item');
    const tabPanes = document.querySelectorAll('.tab-pane');

    // Dashboard fields
    const sidebarPaperTitle = document.getElementById('sidebar-paper-title');
    const sidebarPaperAuthors = document.getElementById('sidebar-paper-authors');
    const paperDisplayTitle = document.getElementById('paper-display-title');
    const paperDisplayAuthors = document.getElementById('paper-display-authors');
    const paperAbstract = document.getElementById('paper-abstract');
    const paperTakeaways = document.getElementById('paper-takeaways');
    const paperMethodology = document.getElementById('paper-methodology');
    const paperResults = document.getElementById('paper-results');
    const paperLimitations = document.getElementById('paper-limitations');
    const flashcardsCount = document.getElementById('flashcards-count');

    // Flashcard fields
    const flashcard = document.getElementById('flashcard');
    const flashcardQuestionText = document.getElementById('flashcard-question-text');
    const flashcardAnswerText = document.getElementById('flashcard-answer-text');
    const btnPrevCard = document.getElementById('btn-prev-card');
    const btnNextCard = document.getElementById('btn-next-card');
    const btnMasteredCard = document.getElementById('btn-mastered-card');
    const btnResetFlashcards = document.getElementById('btn-reset-flashcards');
    const flashcardIndexText = document.getElementById('flashcard-index-text');
    const flashcardScore = document.getElementById('flashcard-score');
    const flashcardSectionSelect = document.getElementById('flashcard-section-select');
    const flashcardSectionBadgeFront = document.getElementById('flashcard-section-badge-front');
    const flashcardSectionBadgeBack = document.getElementById('flashcard-section-badge-back');
    // Chat fields
    const chatMessagesContainer = document.getElementById('chat-messages-container');
    const chatInput = document.getElementById('chat-input');
    const btnSendChat = document.getElementById('btn-send-chat');

    // Export fields
    const btnDownloadMd = document.getElementById('btn-download-md');

    // State
    let selectedFile = null;
    let currentAnalysis = null;
    let currentFlashcards = [];
    let currentCardIndex = 0;
    let masteredCards = new Set(); // Stores indices of mastered flashcards
    let chatHistory = []; // Format: {role: "user"|"model", text: "..."}

    // --- FILE DRAG & DROP & SELECT ---

    // Trigger file input click
    dropZone.addEventListener('click', (e) => {
        // Prevent label click bubbling issue
        if (e.target.tagName !== 'LABEL') {
            fileInput.click();
        }
    });

    // Handle drag events
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        }, false);
    });

    // Handle drop
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    // Handle file input change
    fileInput.addEventListener('change', (e) => {
        if (fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });

    function handleFileSelect(file) {
        if (file.type !== 'application/pdf' && !file.name.endsWith('.pdf')) {
            alert('Please select a PDF research paper.');
            return;
        }

        selectedFile = file;
        previewFilename.textContent = file.name;
        previewFilesize.textContent = formatBytes(file.size);

        dropZone.classList.add('hidden');
        filePreviewContainer.classList.remove('hidden');
    }

    btnRemoveFile.addEventListener('click', () => {
        selectedFile = null;
        fileInput.value = '';
        filePreviewContainer.classList.add('hidden');
        dropZone.classList.remove('hidden');
    });

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    // --- UPLOAD & ANALYSIS CALL ---
    btnAnalyze.addEventListener('click', async () => {
        if (!selectedFile) return;

        // Reset state
        masteredCards.clear();
        chatHistory = [];
        currentCardIndex = 0;

        // UI transitions
        uploadSection.classList.add('hidden');
        loadingSection.classList.remove('hidden');
        btnNewUpload.classList.add('hidden');

        // Progress updates
        updateProgressSteps(1);

        const formData = new FormData();
        formData.append('file', selectedFile);

        // Simulated steps intervals to keep the user engaged
        let stepInterval = setTimeout(() => {
            updateProgressSteps(2);
        }, 3000);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Server returned an error during analysis.');
            }

            clearTimeout(stepInterval);
            updateProgressSteps(3);

            // Give a short delay to appreciate the step completion animation
            setTimeout(() => {
                renderDashboard(data);
            }, 1000);

        } catch (error) {
            clearTimeout(stepInterval);
            loggerError(error.message);
            alert(`Analysis Failed: ${error.message}`);
            // Return to upload
            loadingSection.classList.add('hidden');
            uploadSection.classList.remove('hidden');
        }
    });

    function updateProgressSteps(activeStep) {
        if (activeStep === 1) {
            step1.className = 'step active';
            step2.className = 'step';
            step3.className = 'step';
        } else if (activeStep === 2) {
            step1.className = 'step completed';
            step2.className = 'step active';
            step3.className = 'step';
        } else if (activeStep === 3) {
            step1.className = 'step completed';
            step2.className = 'step completed';
            step3.className = 'step active';
        }
    }

    function loggerError(message) {
        console.error(`[API Error]: ${message}`);
    }

    // --- RENDER DASHBOARD ---
    function renderDashboard(data) {
        currentAnalysis = data;
        currentFlashcards = data.flashcards || [];

        // Title and Meta
        const title = data.title || selectedFile.name.replace('.pdf', '');
        const authors = data.authors || 'Unknown Authors';

        sidebarPaperTitle.textContent = title;
        sidebarPaperAuthors.textContent = authors;
        paperDisplayTitle.textContent = title;
        paperDisplayAuthors.textContent = authors;

        // Check if fallback mode is active
        const fallbackBadge = document.getElementById('fallback-badge');
        if (data.fallback) {
            fallbackBadge.classList.remove('hidden');
        } else {
            fallbackBadge.classList.add('hidden');
        }

        // Abstract
        paperAbstract.innerHTML = parseMarkdown(data.abstract || 'No abstract available.');

        // Key Takeaways
        paperTakeaways.innerHTML = '';
        if (data.key_findings && data.key_findings.length > 0) {
            data.key_findings.forEach(finding => {
                const li = document.createElement('li');
                li.textContent = finding;
                paperTakeaways.appendChild(li);
            });
        } else {
            paperTakeaways.innerHTML = '<li>No key takeaways generated.</li>';
        }

        // Technical Breakdown Details
        paperMethodology.innerHTML = parseMarkdown(data.methodology || 'Methodology description not found.');
        paperResults.innerHTML = parseMarkdown(data.results || 'Experimental results not found.');
        paperLimitations.innerHTML = parseMarkdown(data.limitations || 'Limitations discussion not found.');

        // Flashcard Badges and setup
        flashcardsCount.textContent = currentFlashcards.length;
        initFlashcards();

        // Reset Chat UI
        resetChatUI();

        // Switch panel views
        loadingSection.classList.add('hidden');
        dashboardSection.classList.remove('hidden');
        btnNewUpload.classList.remove('hidden');

        // Always trigger Overview tab on load
        triggerTab('tab-overview');
    }

    // Reset back to upload view
    btnNewUpload.addEventListener('click', () => {
        // Reset inputs
        selectedFile = null;
        fileInput.value = '';
        filePreviewContainer.classList.add('hidden');
        dropZone.classList.remove('hidden');

        const fallbackBadge = document.getElementById('fallback-badge');
        if (fallbackBadge) {
            fallbackBadge.classList.add('hidden');
        }

        // Transition views
        dashboardSection.classList.add('hidden');
        btnNewUpload.classList.add('hidden');
        uploadSection.classList.remove('hidden');
    });

    // --- TAB SWITCHING INTERACTION ---
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetTab = item.getAttribute('data-tab');
            triggerTab(targetTab);
        });
    });

    function triggerTab(tabId) {
        // Update active class on nav buttons
        navItems.forEach(nav => {
            if (nav.getAttribute('data-tab') === tabId) {
                nav.classList.add('active');
            } else {
                nav.classList.remove('active');
            }
        });

        // Show corresponding pane
        tabPanes.forEach(pane => {
            if (pane.id === tabId) {
                pane.classList.add('active');
            } else {
                pane.classList.remove('active');
            }
        });
    }

    // --- FLASHCARDS CODE ---
    let activeFlashcards = [];

    // Trigger update when section changes
    flashcardSectionSelect.addEventListener('change', () => {
        filterFlashcards();
    });

    function filterFlashcards() {
        const selectedSection = flashcardSectionSelect.value;
        if (selectedSection === 'all') {
            activeFlashcards = [...currentFlashcards];
        } else {
            activeFlashcards = currentFlashcards.filter(card => {
                return card.section && card.section.toLowerCase() === selectedSection.toLowerCase();
            });
        }
        currentCardIndex = 0;
        showFlashcard(currentCardIndex);
        updateMasteryScore();
    }

    function initFlashcards() {
        if (currentFlashcards.length === 0) {
            flashcardQuestionText.textContent = "No flashcards generated.";
            flashcardAnswerText.textContent = "Please try again or upload a different paper.";
            btnPrevCard.disabled = true;
            btnNextCard.disabled = true;
            btnMasteredCard.disabled = true;
            return;
        }

        // Reset section select to 'all'
        flashcardSectionSelect.value = 'all';
        filterFlashcards();
    }

    function showFlashcard(index) {
        // Ensure card is flipped back to front on change
        flashcard.classList.remove('flipped');

        if (activeFlashcards.length === 0) {
            flashcardQuestionText.textContent = "No flashcards in this section.";
            flashcardAnswerText.textContent = "Select another section to study.";
            flashcardSectionBadgeFront.textContent = "Empty";
            flashcardSectionBadgeBack.textContent = "Empty";
            btnPrevCard.disabled = true;
            btnNextCard.disabled = true;
            btnMasteredCard.disabled = true;
            flashcardIndexText.textContent = "Card 0 of 0";
            return;
        }

        const cardData = activeFlashcards[index];
        const isMastered = masteredCards.has(cardData.front);

        // Set texts after a tiny timeout to allow transition if it was flipped
        setTimeout(() => {
            flashcardQuestionText.textContent = cardData.front;
            flashcardAnswerText.textContent = cardData.back;

            // Set section text
            const sectionText = cardData.section || "General";
            flashcardSectionBadgeFront.textContent = sectionText;
            flashcardSectionBadgeBack.textContent = sectionText;

            // Update badge CSS classes to match color coding
            ['Abstract', 'Introduction', 'Methodology', 'Results', 'Limitations'].forEach(sec => {
                flashcardSectionBadgeFront.classList.remove(`badge-${sec}`);
                flashcardSectionBadgeBack.classList.remove(`badge-${sec}`);
            });
            if (['Abstract', 'Introduction', 'Methodology', 'Results', 'Limitations'].includes(sectionText)) {
                flashcardSectionBadgeFront.classList.add(`badge-${sectionText}`);
                flashcardSectionBadgeBack.classList.add(`badge-${sectionText}`);
            }

            // Highlight mastered status
            if (isMastered) {
                flashcard.querySelector('.flashcard-front').style.borderColor = 'var(--success)';
            } else {
                flashcard.querySelector('.flashcard-front').style.borderColor = 'var(--border-color)';
            }
        }, 150);

        // Update progress texts
        flashcardIndexText.textContent = `Card ${index + 1} of ${activeFlashcards.length}`;

        // Disable/enable controls
        btnPrevCard.disabled = index === 0;
        btnNextCard.disabled = index === activeFlashcards.length - 1;
        btnMasteredCard.disabled = false;

        // Toggle text on Mastered Button
        if (isMastered) {
            btnMasteredCard.innerHTML = '<i class="fa-solid fa-check-double"></i> Mastered!';
            btnMasteredCard.className = 'btn btn-success';
        } else {
            btnMasteredCard.innerHTML = '<i class="fa-solid fa-check"></i> Mark Mastered';
            btnMasteredCard.className = 'btn btn-secondary';
        }
    }

    // Toggle card flip
    flashcard.addEventListener('click', () => {
        if (activeFlashcards.length > 0) {
            flashcard.classList.toggle('flipped');
        }
    });

    // Previous Button
    btnPrevCard.addEventListener('click', () => {
        if (currentCardIndex > 0) {
            currentCardIndex--;
            showFlashcard(currentCardIndex);
        }
    });

    // Next Button
    btnNextCard.addEventListener('click', () => {
        if (currentCardIndex < activeFlashcards.length - 1) {
            currentCardIndex++;
            showFlashcard(currentCardIndex);
        }
    });

    // Mark Mastered Button
    btnMasteredCard.addEventListener('click', (e) => {
        e.stopPropagation(); // Avoid flipping the card when clicking button
        if (activeFlashcards.length === 0) return;

        const cardData = activeFlashcards[currentCardIndex];
        const isMastered = masteredCards.has(cardData.front);

        if (isMastered) {
            masteredCards.delete(cardData.front);
        } else {
            masteredCards.add(cardData.front);
            // Visual feedback - glow border briefly
            flashcard.querySelector('.flashcard-front').style.borderColor = 'var(--success)';
            // Auto move to next card after a short delay
            if (currentCardIndex < activeFlashcards.length - 1) {
                setTimeout(() => {
                    currentCardIndex++;
                    showFlashcard(currentCardIndex);
                }, 500);
            }
        }

        showFlashcard(currentCardIndex);
        updateMasteryScore();
    });

    // Reset Mastery Button
    btnResetFlashcards.addEventListener('click', () => {
        masteredCards.clear();
        showFlashcard(currentCardIndex);
        updateMasteryScore();
    });

    function updateMasteryScore() {
        const activeMasteredCount = activeFlashcards.filter(card => masteredCards.has(card.front)).length;
        flashcardScore.textContent = `${activeMasteredCount} / ${activeFlashcards.length}`;
    }

    // --- CHAT INTERACTION ASSISTANT ---
    function resetChatUI() {
        // Remove all messages except the first assistant welcome message
        const welcomeMessage = chatMessagesContainer.querySelector('.message.assistant');
        chatMessagesContainer.innerHTML = '';
        if (welcomeMessage) {
            chatMessagesContainer.appendChild(welcomeMessage);
        }
        chatInput.value = '';
    }

    // Handle user sending message
    async function sendMessage(text) {
        if (!text.trim() || !currentAnalysis) return;

        // Clear input
        chatInput.value = '';
        chatInput.style.height = 'auto'; // Reset text area height

        // 1. Render User Message
        appendMessageBubble('user', text);
        chatHistory.push({ role: 'user', text: text });

        // 2. Render Typing Indicator
        const typingIndicator = appendTypingIndicator();
        chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;

        try {
            // Send payload to backend
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    paper_id: currentAnalysis.paper_id,
                    message: text,
                    history: chatHistory.slice(0, -1) // Send history excluding the current query
                })
            });

            const data = await response.json();

            // Remove typing indicator
            typingIndicator.remove();

            if (!response.ok) {
                throw new Error(data.error || 'Server error during chat response.');
            }

            const aiReply = data.response;
            appendMessageBubble('assistant', aiReply);
            chatHistory.push({ role: 'model', text: aiReply });

        } catch (error) {
            typingIndicator.remove();
            appendMessageBubble('assistant', `⚠️ Sorry, I encountered an error: ${error.message}`);
        }

        // Scroll to bottom
        chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
    }

    function appendMessageBubble(role, text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.innerHTML = role === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        if (role === 'assistant') {
            contentDiv.innerHTML = parseMarkdown(text);
        } else {
            const p = document.createElement('p');
            p.textContent = text;
            contentDiv.appendChild(p);
        }

        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        chatMessagesContainer.appendChild(messageDiv);
    }

    function appendTypingIndicator() {
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'message assistant typing-indicator-container';

        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.innerHTML = '<i class="fa-solid fa-robot"></i>';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = `
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;

        indicatorDiv.appendChild(avatarDiv);
        indicatorDiv.appendChild(contentDiv);
        chatMessagesContainer.appendChild(indicatorDiv);
        return indicatorDiv;
    }

    // Simplistic markdown parser for chatbot UI
    function parseMarkdown(text) {
        // Escaping HTML characters first to prevent injection
        let escaped = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Format headers (### Header, ## Header, # Header)
        escaped = escaped.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
        escaped = escaped.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
        escaped = escaped.replace(/^# (.*?)$/gm, '<h1>$1</h1>');

        // Format bold (**text**)
        escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Format italic (*text*)
        escaped = escaped.replace(/\*(.*?)\*/g, '<em>$1</em>');

        // Format code blocks (```code```)
        escaped = escaped.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

        // Format inline code (`code`)
        escaped = escaped.replace(/`(.*?)`/g, '<code>$1</code>');

        // Format unordered list items (lines starting with - or * )
        let lines = escaped.split('\n');
        let inList = false;
        let processedLines = [];

        lines.forEach(line => {
            const trimmed = line.trim();
            if (trimmed.startsWith('<h3>') || trimmed.startsWith('<h2>') || trimmed.startsWith('<h1>')) {
                if (inList) {
                    processedLines.push('</ul>');
                    inList = false;
                }
                processedLines.push(line);
            } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                if (!inList) {
                    processedLines.push('<ul>');
                    inList = true;
                }
                const content = trimmed.substring(2);
                processedLines.push(`<li>${content}</li>`);
            } else {
                if (inList) {
                    processedLines.push('</ul>');
                    inList = false;
                }
                processedLines.push(line);
            }
        });
        if (inList) {
            processedLines.push('</ul>');
        }

        // Convert double breaks to paragraph breaks, single breaks to <br>
        let result = processedLines.join('\n');

        // Group blocks (paragraphs and lists)
        let blocks = result.split(/\n\n+/);
        blocks = blocks.map(block => {
            const trimmed = block.trim();
            if (trimmed.startsWith('<ul>') || trimmed.startsWith('<pre>') || trimmed.startsWith('<h1>') || trimmed.startsWith('<h2>') || trimmed.startsWith('<h3>')) {
                return trimmed;
            }
            return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
        });

        return blocks.join('');
    }

    // Trigger on send button click
    btnSendChat.addEventListener('click', () => {
        const text = chatInput.value;
        sendMessage(text);
    });

    // Trigger on enter key press (but shift+enter adds new line)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            const text = chatInput.value;
            sendMessage(text);
        }
    });

    // Auto-resize chat input text area
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight) + 'px';
    });

    // Attach click events to suggested prompts
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('suggested-prompt-btn')) {
            const promptText = e.target.textContent;
            sendMessage(promptText);
        }
    });

    // --- MARKDOWN SUMMARY EXPORT ---
    btnDownloadMd.addEventListener('click', () => {
        if (!currentAnalysis) return;

        const title = currentAnalysis.title || 'Analysis';
        const authors = currentAnalysis.authors || 'Unknown';

        let md = `# ${title}\n\n`;
        md += `**Authors:** ${authors}\n\n`;
        md += `## Abstract\n${currentAnalysis.abstract || ''}\n\n`;

        md += `## Key Findings & Contributions\n`;
        if (currentAnalysis.key_findings) {
            currentAnalysis.key_findings.forEach(kf => {
                md += `- ${kf}\n`;
            });
        }
        md += `\n`;

        md += `## Methodology\n${currentAnalysis.methodology || ''}\n\n`;
        md += `## Experimental Results\n${currentAnalysis.results || ''}\n\n`;
        md += `## Limitations & Future Work\n${currentAnalysis.limitations || ''}\n\n`;

        md += `## Flashcards Study Set\n`;
        if (currentAnalysis.flashcards) {
            currentAnalysis.flashcards.forEach((fc, idx) => {
                md += `### Flashcard ${idx + 1}\n`;
                md += `**Question:** ${fc.front}\n`;
                md += `**Answer:** ${fc.back}\n\n`;
            });
        }

        // Trigger file download
        const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `${title.toLowerCase().replace(/[^a-z0-9]+/g, '_')}_summary.md`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    });
});
