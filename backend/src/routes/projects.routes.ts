import { Router } from "express";
import {
  deleteProject,
  listProjects,
  readProject,
  renameProject,
  writeProject,
} from "../services/project.service.js";
import { cancelYouTubeDownload } from "../services/youtube.service.js";

export const projectsRouter = Router();

// GET /api/projects — list all projects (dashboard card data)
projectsRouter.get("/", (_request, response) => {
  try {
    const projects = listProjects();
    response.status(200).json({ projects });
  } catch (error: any) {
    response.status(500).json({ message: error.message });
  }
});

// GET /api/projects/:jobId — single project info (used for session recovery validation)
projectsRouter.get("/:jobId", (request, response) => {
  const project = readProject(request.params.jobId);
  if (!project) {
    response.status(404).json({ message: "Project not found." });
    return;
  }
  response.status(200).json(project);
});

// PATCH /api/projects/:jobId — update project info (rename, lastActiveStep, settings)
projectsRouter.patch("/:jobId", (request, response) => {
  const { name, lastActiveStep, settings } = request.body;
  const project = writeProject(request.params.jobId, {
    ...(typeof name === "string" && name.trim() ? { name: name.trim() } : {}),
    ...(typeof lastActiveStep === "string" ? { lastActiveStep } : {}),
    ...(settings && typeof settings === "object" ? { settings } : {}),
  });
  if (!project) {
    response.status(404).json({ message: "Project not found." });
    return;
  }
  response.status(200).json(project);
});

// DELETE /api/projects/:jobId — permanently delete project and ALL associated files
projectsRouter.delete("/:jobId", (request, response) => {
  try {
    const project = readProject(request.params.jobId);
    if (!project) {
      response.status(404).json({ message: "Project not found." });
      return;
    }
    cancelYouTubeDownload(request.params.jobId);
    deleteProject(request.params.jobId);
    response.status(200).json({ success: true, message: "Project deleted successfully." });
  } catch (error: any) {
    response.status(500).json({ success: false, message: error.message });
  }
});
