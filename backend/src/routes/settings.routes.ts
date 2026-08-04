import fs from "fs";
import path from "path";
import { spawn } from "child_process";
import { Router } from "express";
import { readSettings, writeSettings } from "../services/settings.service.js";

export const settingsRouter = Router();

settingsRouter.get("/", (_request, response) => {
  response.status(200).json(readSettings());
});

settingsRouter.put("/", (request, response) => {
  const settings = writeSettings(request.body);
  response.status(200).json(settings);
});

settingsRouter.get("/music-status", (_request, response) => {
  const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");
  const musicDir = path.join(storageRoot, "music");
  const extensions = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"];

  const hasMusic =
    fs.existsSync(musicDir) &&
    fs.readdirSync(musicDir).some((file) =>
      extensions.includes(path.extname(file).toLowerCase())
    );

  response.status(200).json({ hasMusic });
});

settingsRouter.post("/download-music", (_request, response) => {
  const root = path.resolve(process.cwd(), "..");
  const scriptPath = path.join(root, "download_music.py");

  const child = spawn("python", [scriptPath], { cwd: root });

  let output = "";
  child.stdout.on("data", (data) => {
    output += data.toString();
  });

  child.stderr.on("data", (data) => {
    output += data.toString();
  });

  child.on("close", (code) => {
    if (code === 0) {
      response.status(200).json({ success: true, message: "Music downloaded successfully.", output });
    } else {
      response.status(500).json({ success: false, message: "Failed to download music.", output });
    }
  });
});

function getDirSize(dirPath: string): number {
  let size = 0;
  if (!fs.existsSync(dirPath)) return 0;
  const stats = fs.statSync(dirPath);
  if (stats.isFile()) return stats.size;
  if (stats.isDirectory()) {
    const files = fs.readdirSync(dirPath);
    for (const file of files) {
      size += getDirSize(path.join(dirPath, file));
    }
  }
  return size;
}

function cleanTempDir(dirPath: string) {
  if (!fs.existsSync(dirPath)) return;
  const files = fs.readdirSync(dirPath);
  for (const file of files) {
    fs.rmSync(path.join(dirPath, file), { recursive: true, force: true });
  }
}

settingsRouter.get("/temp-size", (_request, response) => {
  const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");
  const tempDir = path.join(storageRoot, "temp");
  const size = getDirSize(tempDir);
  response.status(200).json({ size });
});

settingsRouter.post("/clean-temp", (_request, response) => {
  const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");
  const tempDir = path.join(storageRoot, "temp");
  try {
    cleanTempDir(tempDir);
    response.status(200).json({ success: true, message: "Temp files cleared successfully." });
  } catch (error) {
    response.status(500).json({ success: false, message: "Failed to clear temp files." });
  }
});
