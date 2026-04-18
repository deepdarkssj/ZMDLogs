import express from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { createServer as createViteServer } from "vite";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const server = createServer(app);
  const wss = new WebSocketServer({ server });

  const PORT = 3000;

  // Mock data for skills
  const skills = [
    { id: "jinpu", name: "Jinpu", cooldown: 30, remaining: 23.7 },
    { id: "shifu", name: "Shifu", cooldown: 30, remaining: 23.7 },
    { id: "meikyo", name: "Meikyo ...", cooldown: 60, remaining: 38.7 },
    { id: "ikishoten", name: "Ikishoten", cooldown: 120, remaining: 43.7 },
    { id: "hissatsu", name: "Hissats...", cooldown: 120, remaining: 103.7 },
  ];

  wss.on("connection", (ws) => {
    console.log("Client connected");
    
    // Send initial state
    ws.send(JSON.stringify({ type: "INIT", skills }));

    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        // Simulate cooldown ticking down
        skills.forEach(skill => {
          if (skill.remaining > 0) {
            skill.remaining = Math.max(0, skill.remaining - 0.1);
          } else {
            // Reset for demo purposes
            skill.remaining = skill.cooldown;
          }
        });
        ws.send(JSON.stringify({ type: "UPDATE", skills }));
      }
    }, 100);

    ws.on("close", () => {
      clearInterval(interval);
      console.log("Client disconnected");
    });
  });

  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  server.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
