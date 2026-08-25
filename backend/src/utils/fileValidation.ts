const allowedExtensions = new Set(["mp4", "mov", "avi", "mkv", "webm"]);
const allowedMimePrefixes = ["video/"];
const allowedMimeTypes = new Set(["application/octet-stream"]);

export function validateVideoFile(originalName: string, mimetype: string) {
  const extension = originalName.split(".").pop()?.toLowerCase();

  if (!extension || !allowedExtensions.has(extension)) {
    return {
      ok: false,
      message: "Format not supported. Use MP4, MOV, AVI, MKV, or WEBM."
    };
  }

  const validMime =
    allowedMimePrefixes.some((prefix) => mimetype.startsWith(prefix)) ||
    allowedMimeTypes.has(mimetype);

  if (!validMime) {
    return {
      ok: false,
      message: "Selected file does not look like a video."
    };
  }

  return { ok: true, message: "Valid video file." };
}
