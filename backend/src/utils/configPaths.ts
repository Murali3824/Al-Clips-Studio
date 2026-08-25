import fs from "fs";
import path from "path";

const configRoot = path.resolve(process.env.CONFIG_PATH ?? "../config");

export function getUserSettingsPath() {
  fs.mkdirSync(configRoot, { recursive: true });
  return path.join(configRoot, "user.settings.json");
}
