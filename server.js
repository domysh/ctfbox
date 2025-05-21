const express = require("express");
const cors = require("cors");
const path = require("path");
const fs = require("fs");

const app = express();
// Enable CORS with permissive settings (disable CORS policy)
app.use(cors({
  origin: '*',
  methods: 'GET,HEAD,PUT,PATCH,POST,DELETE',
  credentials: true,
  preflightContinue: false,
  optionsSuccessStatus: 204
}));
const PORT = process.env.PORT || 3000;
const STATIC_DIR = path.join(__dirname, ".");

// Middleware to handle URLs without .html extension
app.use((req, res, next) => {
    // Don't modify API requests or requests for files with extensions
    if (req.path.startsWith("/api/") || path.extname(req.path) !== "") {
        return next();
    }

    // For root path
    if (req.path === "/") {
        return next();
    }

    // Check if there's an HTML file that matches the clean URL
    const htmlFilePath = path.join(STATIC_DIR, `${req.path}.html`);
    fs.access(htmlFilePath, fs.constants.F_OK, (err) => {
        if (!err) {
            // File exists, serve it
            res.sendFile(htmlFilePath);
        } else {
            // No exact match, check if it's a directory with an index.html
            const indexPath = path.join(STATIC_DIR, req.path, "index.html");
            fs.access(indexPath, fs.constants.F_OK, (err) => {
                if (!err) {
                    // Directory index exists, serve it
                    res.sendFile(indexPath);
                } else {
                    // No match, continue to next middleware
                    next();
                }
            });
        }
    });
});

// Serve static files from the static-site directory
app.use(express.static(STATIC_DIR));

// Default route handler for any remaining routes
app.use((req, res) => {
    // Check if we're missing the .html extension
    const htmlPath = path.join(STATIC_DIR, `${req.path}.html`);
    fs.access(htmlPath, fs.constants.F_OK, (err) => {
        if (!err) {
            res.sendFile(htmlPath);
        } else {
            // Try serving index.html for SPA client-side routing
            const indexPath = path.join(STATIC_DIR, "index.html");
            fs.access(indexPath, fs.constants.F_OK, (err) => {
                if (!err) {
                    res.sendFile(indexPath);
                } else {
                    res.status(404).send("Not found");
                }
            });
        }
    });
});

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}/`);
    console.log(`Serving static files from: ${STATIC_DIR}`);
});
