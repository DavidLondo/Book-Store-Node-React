import express from 'express';
import colors from 'colors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import bookRoutes from './routes/bookRoutes.js';

dotenv.config();
const app = express();
const PORT = process.env.PORT || 5001;

app.use('/api/books', bookRoutes);
app.get('/healthz', (_req, res) => res.status(200).send('ok'));

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

if (process.env.NODE_ENV === 'production') {
  const frontendBuildPath = path.resolve(__dirname, '../frontend/build');
  app.use(express.static(frontendBuildPath));
  app.get('/', (_req, res) => res.sendFile(path.join(frontendBuildPath, 'index.html')));
  app.get(/^\/(?!api\/).*/, (_req, res) => res.sendFile(path.join(frontendBuildPath, 'index.html')));
} else {
  app.get('/', (_req, res) => res.send('API is running...'));
}

app.listen(PORT, () => {
  console.log(`Server running in ${process.env.NODE_ENV} and listening on PORT ${PORT}`.blue);
});

