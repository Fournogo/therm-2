const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/data', // or whatever route your Flask API uses
    createProxyMiddleware({
      target: 'http://10.1.1.11:5023', // Flask server URL
      changeOrigin: true,
    })
  );
};
