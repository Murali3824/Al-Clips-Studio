import cors from "cors";
import dotenv from "dotenv";
import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";
import { healthRouter } from "./routes/health.routes.js";
import { exportRouter } from "./routes/export.routes.js";
import { processRouter } from "./routes/process.routes.js";
import { projectsRouter } from "./routes/projects.routes.js";
import { resultsRouter } from "./routes/results.routes.js";
import { settingsRouter } from "./routes/settings.routes.js";
import { storageRouter } from "./routes/storage.routes.js";
import { uploadRouter } from "./routes/upload.routes.js";

dotenv.config();

const app = express();
const httpServer = createServer(app);
const port = Number(process.env.PORT ?? 3001);
const frontendUrl = process.env.FRONTEND_URL ?? "http://localhost:5173";

export const io = new Server(httpServer, {
  cors: {
    origin: frontendUrl
  }
});

app.use(cors({ origin: frontendUrl }));
app.use(express.json());
app.use("/api/export", exportRouter);
app.use("/api/health", healthRouter);
app.use("/api/process", processRouter);
app.use("/api/projects", projectsRouter);
app.use("/api/results", resultsRouter);
app.use("/api/settings", settingsRouter);
app.use("/api/storage", storageRouter);
app.use("/api/upload", uploadRouter);

io.on("connection", (socket) => {
  socket.emit("connected", { ok: true });
});

httpServer.listen(port, () => {
  console.log(`Backend listening on http://localhost:${port}`);
});
