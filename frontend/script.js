// Global variable to hold the Monaco Editor instance
let editor;

// Define Snippets
const snippets = {
    "hello": 'print("Hello, world!")',
    "loop": '# This loop prints numbers from 1 to 3\nprint("Counting from 1 to 3:")\nfor i in range(1, 4):\n    print(i)',
    "input_name": '# Asks for a name and greets the user\nname = input("Enter your name: ")\nprint(f"Hello, {name}!")',
    "function_def": '# Defines a simple function and calls it\ndef greet(person_name):\n    return f"Hi there, {person_name}!"\n\nmessage = greet("Alex")\nprint(message)\nprint(greet("Python Coder"))'
};

// This is Monaco Editor's way of loading.
require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.47.0/min/vs' }});
require(['vs/editor/editor.main'], function() {
    // Initialize the Monaco Editor
    editor = monaco.editor.create(document.getElementById('editor'), {
        value: snippets["hello"], // Start with the "Hello World" snippet or any default code
        language: 'python',
        theme: 'vs-dark',
        automaticLayout: true,
        minimap: { enabled: true }
    });
    console.log("Monaco Editor initialized.");

    // --- SNIPPET SELECTOR LOGIC ---
    // Moved here to ensure 'editor' is defined
    const snippetSelector = document.getElementById('snippetSelector');
    if (snippetSelector) {
        snippetSelector.addEventListener('change', function() {
            const selectedSnippetKey = this.value;
            if (selectedSnippetKey && snippets[selectedSnippetKey]) {
                // Preserve undo history by using an edit operation
                const currentModel = editor.getModel();
                if (currentModel) {
                    currentModel.pushEditOperations(
                        [], // previous cursors
                        [{
                            range: currentModel.getFullModelRange(), // range to replace
                            text: snippets[selectedSnippetKey]    // new text
                        }],
                        () => null // undo stop before
                    );
                } else { // Fallback if model is not available (should not happen)
                    editor.setValue(snippets[selectedSnippetKey]);
                }
                this.value = ""; // Reset selector to default "-- Select a snippet --"
            }
        });
        console.log("Snippet selector event listener attached.");
    }
    // --- END SNIPPET SELECTOR LOGIC ---
});

// Get references to the HTML elements
const runButton = document.getElementById('runButton');
const terminalOutput = document.getElementById('terminal');
const inputField = document.getElementById('inputField');
const clearTerminalButton = document.getElementById('clearTerminalButton'); // Get clear button

// Function to add messages to our pseudo-terminal
function addToTerminal(message, type = 'output') {
    const p = document.createElement('p');
    p.textContent = message;

    if (type === 'error') {
        p.style.color = 'red';
    } else if (type === 'info') {
        p.style.color = '#aaa';
        p.style.fontStyle = 'italic';
    }
    terminalOutput.appendChild(p);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// Event listener for the "Run Code" button
if (runButton) {
    runButton.addEventListener('click', async () => {
        if (!editor) {
            addToTerminal("Editor not initialized yet.", 'error');
            return;
        }

        runButton.disabled = true;
        runButton.textContent = 'Running...';
        // terminalOutput.innerHTML = ''; // Optional: Clear terminal on run
        // initializeTerminal(); // Or re-initialize with welcome messages
        addToTerminal("Executing code...", 'info');

        const code = editor.getValue();
        const userInput = inputField.value;

        try {
            const response = await fetch('http://localhost:5000/api/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, input: userInput }),
            });

            if (!response.ok) {
                let errorMsg = `Backend error: ${response.status} ${response.statusText}`;
                try {
                    const errorBody = await response.text();
                    if (errorBody) {
                        try {
                            const jsonError = JSON.parse(errorBody);
                            errorMsg += `\nDetails: ${jsonError.error || errorBody}`;
                        } catch { errorMsg += `\nDetails: ${errorBody}`; }
                    }
                } catch { /* Ignore if reading body fails */ }
                throw new Error(errorMsg);
            }

            const result = await response.json();
            if (result.error) {
                addToTerminal(`Error:\n${result.error}`, 'error');
            } else {
                addToTerminal(result.output || "(No output from script)");
            }
        } catch (error) {
            console.error("Frontend: Error during communication with backend:", error);
            addToTerminal(`Frontend Error: ${error.message}`, 'error');
        } finally {
            runButton.disabled = false;
            runButton.textContent = 'Run Code';
        }
    });
}

// Event listener for "Clear Terminal" button
if (clearTerminalButton) {
    clearTerminalButton.addEventListener('click', () => {
        terminalOutput.innerHTML = '';
        addToTerminal("Terminal cleared.", "info");
    });
}

// Event listener for Ctrl+Enter in input field
if (inputField) {
    inputField.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            if (runButton) runButton.click();
        }
    });
}

// Initial message setup
function initializeTerminal() {
    // terminalOutput.innerHTML = ''; // Optional: Clear if you want a fresh start on page load
    addToTerminal("PyPad - Dockerized Python Editor Ready!");

}

// Run initial setup
initializeTerminal();
console.log("SCRIPT.JS (with snippets) LOADED - " + new Date().toLocaleTimeString());