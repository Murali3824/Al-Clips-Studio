#!/bin/bash

echo "=========================================="
echo " AI Shorts Generator - Project Setup (Unix)"
echo "=========================================="
echo ""

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed. Please install Node.js (v20+ recommended)."
    exit 1
fi
echo "Node.js is installed."

# Check Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python is not installed. Please install Python (v3.10+ recommended)."
    exit 1
fi
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi
echo "Python is installed."

# Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "[WARNING] FFmpeg is not installed. FFmpeg is required for video processing."
else
    echo "FFmpeg is installed."
fi

echo ""
echo "Installing Backend dependencies..."
cd backend
npm install
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install backend dependencies."
    exit 1
fi
cd ..

echo ""
echo "Installing Frontend dependencies..."
cd frontend
npm install
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install frontend dependencies."
    exit 1
fi
cd ..

echo ""
echo "Installing Python dependencies..."
$PYTHON_CMD -m pip install -r ai/requirements.txt
if [ $? -ne 0 ]; then
    echo "[WARNING] Failed to install python dependencies globally. Trying user mode..."
    $PYTHON_CMD -m pip install --user -r ai/requirements.txt
fi

echo ""
echo "=========================================="
echo " Setup Completed Successfully!"
echo "=========================================="
echo ""
echo "Please ensure Ollama is installed and running:"
echo "  Download from https://ollama.com/ and run 'ollama run llama3:8b'"
echo ""
