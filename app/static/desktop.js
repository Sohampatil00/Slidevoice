/* Only Gemini credentials are editable; saved keys are never returned. */
(async () => {
  const response = await fetch('/api/desktop/settings');
  if (!response.ok) return;
  let settings = await response.json();
  const panel = document.createElement('form');
  panel.innerHTML = `<h3>Gemini scripts</h3><p id="desktop-key-status"></p>
    <label>Gemini API key <input name="gemini" type="password" autocomplete="off" placeholder="Leave blank to keep current key"></label>
    <button class="button" type="submit">Save key</button><p role="status" id="desktop-settings-result"></p>`;
  document.getElementById('desktop-settings').append(panel);
  const setup = document.createElement('section');
  setup.innerHTML = `<h3>Local components</h3>
    <p>Prepare narration models and, on Windows, PowerPoint support. Setup needs internet and several GB of free disk space. Completed components are reused.</p>
    <button class="button" type="button">Prepare / repair components</button>
    <p role="status" aria-live="polite"></p>`;
  document.getElementById('desktop-settings').prepend(setup);
  const setupButton = setup.querySelector('button');
  const setupMessage = setup.querySelector('[role="status"]');
  let timer;
  async function checkSetup() {
    try {
      const status = await api('/api/desktop/setup');
      setupMessage.textContent = status.message;
      setupButton.disabled = status.status === 'running';
      clearTimeout(timer);
      if (status.status === 'running') timer = setTimeout(checkSetup, 2000);
      else if (status.status === 'complete') {
        state.health = await api('/api/health');
        renderConnections(); updateButtons();
      }
    } catch (error) { setupMessage.textContent = error.message; setupButton.disabled = false; }
  }
  setupButton.addEventListener('click', async () => {
    setupButton.disabled = true;
    try { await api('/api/desktop/setup', {method: 'POST'}); await checkSetup(); }
    catch (error) { setupMessage.textContent = error.message; setupButton.disabled = false; }
  });
  await checkSetup();
  function refresh() {
    panel.querySelector('#desktop-key-status').textContent = settings.gemini_configured ? 'Your Gemini key is configured.' : 'Add a Gemini key to generate scripts, or paste your own scripts for free.';
  }
  refresh();
  panel.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {};
    if (panel.elements.gemini.value.trim()) payload.gemini_key = panel.elements.gemini.value.trim();
    const result = panel.querySelector('#desktop-settings-result');
    try {
      settings = await api('/api/desktop/settings', {method: 'PUT', body: payload});
      panel.elements.gemini.value = '';
      refresh();
      state.health = await api('/api/health');
      renderConnections(); updateButtons();
      result.textContent = settings.gemini_configured ? 'Saved. Gemini is ready for script generation.' : 'No key configured. You can still paste your own scripts.';
    } catch (error) { result.textContent = error.message; }
  });
})().catch(() => {});
