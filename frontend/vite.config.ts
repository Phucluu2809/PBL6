import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { datasetPlugin } from './server/dataset.mjs';
export default defineConfig({ plugins: [react(), datasetPlugin()], base: './' });
