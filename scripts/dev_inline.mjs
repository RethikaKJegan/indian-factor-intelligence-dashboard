import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

const server = await createServer({
  configFile: false,
  root: process.cwd(),
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("../src", import.meta.url)),
    },
  },
  optimizeDeps: {
    include: ["@vitejs/plugin-react", "react", "react-dom", "react/jsx-runtime", "lucide-react"],
  },
});

await server.listen();
server.printUrls();
