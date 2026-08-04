import { Router } from "express";
import { createExportZip } from "../services/export.service.js";

export const exportRouter = Router();

exportRouter.get("/:jobId/download", async (request, response, next) => {
  try {
    const clipIds = Array.isArray(request.query.clipId)
      ? request.query.clipId.map(String)
      : request.query.clipId
        ? [String(request.query.clipId)]
        : [];
    const zipPath = await createExportZip(request.params.jobId, clipIds);

    response.download(zipPath, `${request.params.jobId}-export.zip`);
  } catch (error) {
    next(error);
  }
});
