const http = require('http');
const fs = require('fs');
const path = require('path');
const PORT = process.env.PORT || 3003;

const MIME = {
  '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css',
  '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json',
  '.wasm': 'application/wasm', '.map': 'application/json'
};

http.createServer((req, res) => {
  let url = req.url.split('?')[0].replace(/^\/school-tracker/, '') || '/';
  let filePath = path.join(__dirname, url === '/' ? 'index.html' : url);
  if (!fs.existsSync(filePath)) filePath = path.join(__dirname, 'index.html');
  const ext = path.extname(filePath);
  const ct = MIME[ext] || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': ct, 'Cache-Control': 'no-store' });
  fs.createReadStream(filePath).pipe(res);
}).listen(PORT, () => console.log(`School Tracker web on port ${PORT}`));
