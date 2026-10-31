import { defineConfig } from "vite";
import { transitConfig } from "../shared/vite.base.js";

export default defineConfig(transitConfig(Number(process.env.PORT) || 3000));
