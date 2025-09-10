#  Copilot-Monitoring 📊

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<img width="1347" height="676" alt="Capture d’écran 2025-09-10 à 23 04 25" src="https://github.com/user-attachments/assets/072a7e5d-a6f0-43f2-8194-f393b16b7da4" />

A beautiful, real-time dashboard to monitor your local GitHub Copilot API usage. Understand your token consumption, track performance metrics, and get a visual representation of your activity.

---

## ✨ Features

*   **Real-time Dashboard**: See API requests as they happen via a WebSocket connection.
*   **Comprehensive Statistics**: Track total requests, latency, data transfer sizes, and output speed (tokens/sec).
*   **Token Breakdown**: Detailed breakdown of prompt, completion, and total tokens used.
*   **Model Usage**: See token consumption and performance metrics for each model used by Copilot.
*   **Consumption Monitor**: A real-time panel showing your activity over the last hour with a "Consumption Score" and an environmental impact visualization.
*   **Historical View**: A calendar heatmap visualizes your token usage over the past year.
*   **Tech Stack**: Built with `mitmproxy`, `FastAPI` (Python), and `React/TypeScript` (Vite).

<img width="1324" height="750" alt="Capture d’écran 2025-09-10 à 23 05 10" src="https://github.com/user-attachments/assets/9cc9664f-aa97-4f2e-81aa-cee75b6a507f" />

## 🛠️ Installation & Setup

Follow these steps to get your monitoring dashboard up and running.

### 1. Prerequisites

*   **Node.js**: Required for the frontend. You can download it from [nodejs.org](https://nodejs.org/).
*   **Python**: Required for the backend proxy.
*   **mitmproxy**: The core proxy tool. Install it via pip:
    ```bash
    pip install mitmproxy
    ```

### 2. Project Setup

1.  **Clone the repository** (if you haven't already).
2.  **Install Dependencies**:
    Navigate to the root of the project and run the master installation script. This command will install all necessary Node.js and Python dependencies (in dedicated venv) for the entire project.
    ```bash
    npm run install:all
    ```

### 3. mitmproxy Certificate Installation

For `mitmproxy` to inspect Copilot's HTTPS traffic, you must install its root certificate.

1.  Run `mitmproxy` once from your terminal to generate the certificates:
    ```bash
    mitmproxy
    ```
2.  The certificates are typically located in `~/.mitmproxy`. Follow the official instructions for your operating system to install and trust the `mitmproxy-ca-cert.pem` certificate:
    *   [mitmproxy Certificate Installation Guide](https://docs.mitmproxy.org/stable/howto-install-certificates/)

### 4. Configure VS Code Proxy

You need to tell VS Code to route its traffic through `mitmproxy`.

1.  In VS Code, open the Command Palette (`Cmd+Shift+P` on macOS or `Ctrl+Shift+P` on Windows/Linux).
2.  Type `Preferences: Open User Settings (JSON)` and press Enter. This will open your `settings.json` file.
3.  Add the following line to the JSON configuration. This tells VS Code to use the proxy running on port `8080`.

    ```json
    
    {
        // ...
        "http.proxy": "http://127.0.0.1:8080",
        // ...
    }
    ```
    > **Note**: `"http.proxyStrictSSL": false` could be required to allow VS Code to trust the locally installed `mitmproxy` certificate. Remember to remove these settings if you stop using the proxy. (My environnement didn't require it)

### 5. Run the Application

Go to the root folder of the project and run the start script. This will launch the backend server, the mitmproxy instance, and the frontend development server.

```bash
npm start
```

You can now open your browser and navigate to `http://localhost:5173` to see the dashboard.

---

## 💡 Tips & Troubleshooting

### Kill All Processes

If the application quits unexpectedly, background processes might remain active. Use this command on macOS to kill all processes running on the required ports:

```bash
kill -9 $(lsof -t -i :8000 -i :8080 -i :5173)
```

### Quick-start Alias (macOS)

For easy access, you can add a variable/alias to your shell profile (`.zshrc`, `.bash_profile`, etc.) to start the logger instantly from any terminal.

```bash
# Example for .zshrc
alias copilot-monitor="cd /path/to/your/Copilot-Monitoring/ && npm start"
```

---

## 🤝 Contributing

All contributions are welcome! This project was built for the community, and we encourage you to get involved.

*   **Open an Issue**: If you find a bug, have a feature request, or a question, please do not hesitate to open an issue.
*   **Fork and Pull Request**: Feel free to fork the repository and submit a pull request with your changes.

We would love to hear from you!

## 📜 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
