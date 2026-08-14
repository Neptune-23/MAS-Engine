@echo off
echo Starting MCP HTTP Server...
cd /d "D:\Python\Agent\company-ai-toolkit\mcp-server"
"D:\Python\Agent\company-ai-toolkit\mcp-server\venv\Scripts\python.exe" server.py --http
pause