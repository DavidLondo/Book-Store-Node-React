import express from 'express';
import colors from 'colors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import bookRoutes from './routes/bookRoutes.js'


dotenv.config()

const app = express();

const PORT = process.env.PORT || 5001;

app.use('/api/books/', bookRoutes)

// Serve frontend build in production
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

if (process.env.NODE_ENV === 'production') {
  const frontendBuildPath = path.resolve(__dirname, '../frontend/build');
  app.use(express.static(frontendBuildPath));

  // Dedicated health check endpoint for ALB
  app.get('/healthz', (req, res) => {
    res.status(200).send('OK');
  });

  // Serve SPA index at root
  app.get('/', (req, res) => {
    res.sendFile(path.join(frontendBuildPath, 'index.html'));
  });

  // SPA fallback for non-API routes
  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api/')) return next();
    res.sendFile(path.join(frontendBuildPath, 'index.html'));
  });
} else {
  // Dev root
  app.get('/', (req, res) => {
    res.send('API is running...');
  });
}

app.listen(PORT, () => {
  console.log(`Server running in ${process.env.NODE_ENV} and listening on PORT ${PORT}`.blue)
})

