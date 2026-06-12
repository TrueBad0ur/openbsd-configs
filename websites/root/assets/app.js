function tick() {
  const d = new Date();
  document.getElementById('ts').textContent =
    d.toISOString().replace('T',' ').slice(0,19) + ' UTC';
}
tick();
setInterval(tick, 1000);
