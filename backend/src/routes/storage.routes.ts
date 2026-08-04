import { Router } from "express";
import {
  CleanupCategory,
  cleanupStorage,
  getStorageBreakdown,
  checkSourceVideoExists,
} from "../services/storage.service.js";

export const storageRouter = Router();

// GET /api/storage/breakdown — Get storage metrics breakdown
storageRouter.get("/breakdown", (_request, response) => {
  try {
    const breakdown = getStorageBreakdown();
    response.status(200).json(breakdown);
  } catch (error: any) {
    response.status(500).json({ message: error.message || "Failed to calculate storage breakdown." });
  }
});

// POST /api/storage/clean — Execute category storage cleanup safely
storageRouter.post("/clean", (request, response) => {
  try {
    const { category } = request.body as { category?: CleanupCategory };
    const validCategories: CleanupCategory[] = ["temp", "clips", "uploads", "everything"];

    if (!category || !validCategories.includes(category)) {
      response.status(400).json({ message: "Invalid cleanup category specified." });
      return;
    }

    const result = cleanupStorage(category);
    response.status(200).json(result);
  } catch (error: any) {
    response.status(500).json({ message: error.message || "Storage cleanup failed." });
  }
});

// GET /api/storage/check-source/:jobId — Check if original source video exists
storageRouter.get("/check-source/:jobId", (request, response) => {
  try {
    const { jobId } = request.params;
    const exists = checkSourceVideoExists(jobId);
    response.status(200).json({ jobId, exists });
  } catch (error: any) {
    response.status(500).json({ message: error.message || "Failed to check source video." });
  }
});
