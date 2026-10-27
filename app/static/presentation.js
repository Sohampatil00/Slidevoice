/* Slide presentation works with or without narration, including embedded WebViews. */
(() => {
  const dialog = element('presentation');
  const audio = element('presentation-audio');
  let slides = [], index = 0, playing = false, timer = null, revision = 0;
  let ownsFullscreen = false;
  const help = '← / → navigate · Space plays or pauses narration · Esc exits';

  function clearPlayback() {
    revision += 1;
    clearTimeout(timer); timer = null;
    audio.pause();
    audio.removeAttribute('src'); audio.load();
  }
  function updatePlayButton() {
    element('presentation-play').textContent = playing ? 'Pause narration' : 'Play narration';
    element('presentation-play').disabled = !slides[index]?.audio_ready;
  }
  async function playCurrent() {
    if (!playing || !dialog.open) return;
    const slide = slides[index];
    if (!slide.audio_ready) {
      playing = false;
      element('presentation-status').textContent = 'This slide has no narration. Use Next or → to continue.';
      updatePlayButton();
      return;
    }
    const current = revision;
    try {
      await audio.play();
      if (current === revision) element('presentation-status').textContent = 'Playing narration. Slides advance after each clip. ' + help;
    } catch {
      if (current !== revision) return;
      playing = false;
      updatePlayButton();
      element('presentation-status').textContent = 'Audio could not play. Try Play narration again, or advance manually.';
    }
  }
  function showSlide(next) {
    if (next < 0 || next >= slides.length) return;
    clearPlayback();
    index = next;
    const slide = slides[index];
    element('presentation-image').src = slide.image_url;
    element('presentation-image').alt = `Slide ${slide.number}: ${slide.title}`;
    element('presentation-counter').textContent = `${index + 1} / ${slides.length}`;
    element('presentation-prev').disabled = index === 0;
    element('presentation-next').disabled = index === slides.length - 1;
    element('presentation-status').textContent = slide.audio_ready ? help : 'No narration on this slide. Use ← / → to navigate.';
    if (slide.audio_ready) audio.src = slide.audio_url;
    updatePlayButton();
    playCurrent();
  }
  function pause() {
    playing = false;
    revision += 1;
    clearTimeout(timer); timer = null;
    audio.pause();
    updatePlayButton();
    element('presentation-status').textContent = help;
  }
  function togglePlayback() {
    if (playing) { pause(); return; }
    if (!slides[index]?.audio_ready) return;
    if (audio.ended) audio.currentTime = 0;
    playing = true;
    updatePlayButton();
    playCurrent();
  }
  function stop() {
    playing = false;
    clearPlayback();
    if (dialog.open) dialog.close();
    if (ownsFullscreen && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    ownsFullscreen = false;
    if (state.project && slides.length) {
      state.slide = index;
      render();
    }
    element('present-slides').focus();
  }
  element('present-slides').addEventListener('click', () => action(async () => {
    await saveScript();
    if (!state.project?.slides.length) return;
    slides = state.project.slides.slice();
    playing = false;
    element('audio-player').pause();
    element('reference-player').pause();
    element('video-player').pause();
    dialog.showModal();
    document.body.classList.add('presenting');
    showSlide(state.slide);
    element('presentation-close').focus();
  }));
  dialog.addEventListener('close', () => {
    playing = false; clearPlayback(); document.body.classList.remove('presenting');
  });
  dialog.addEventListener('cancel', (event) => { event.preventDefault(); stop(); });
  element('presentation-close').addEventListener('click', stop);
  element('presentation-prev').addEventListener('click', () => showSlide(index - 1));
  element('presentation-next').addEventListener('click', () => showSlide(index + 1));
  element('presentation-play').addEventListener('click', togglePlayback);
  audio.addEventListener('ended', () => {
    if (!playing || !dialog.open) return;
    if (index === slides.length - 1) {
      pause(); element('presentation-status').textContent = 'Presentation finished. Use ← to review or exit.'; return;
    }
    const current = revision;
    const delay = Math.max(0, Number(element('pause').value) || 0) * 1000;
    timer = setTimeout(() => { if (playing && current === revision) showSlide(index + 1); }, delay);
  });
  audio.addEventListener('error', () => {
    if (!audio.getAttribute('src') || !dialog.open) return;
    pause(); element('presentation-status').textContent = 'Narration is unavailable. Use Next to continue.';
  });
  element('presentation-fullscreen').addEventListener('click', async () => {
    try {
      if (window.pywebview?.api?.toggle_fullscreen) {
        const full = await window.pywebview.api.toggle_fullscreen();
        element('presentation-fullscreen').textContent = full ? 'Leave full screen' : 'Full screen';
        return;
      }
      if (document.fullscreenElement) { await document.exitFullscreen(); ownsFullscreen = false; }
      else if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen(); ownsFullscreen = true;
      } else element('presentation-status').textContent = 'Presentation fills the app window. Use the window’s full-screen control to fill your display.';
    } catch {
      element('presentation-status').textContent = 'Presentation fills the app window. Use the window’s full-screen control to fill your display.';
    }
  });
  document.addEventListener('fullscreenchange', () => {
    element('presentation-fullscreen').textContent = document.fullscreenElement ? 'Leave full screen' : 'Full screen';
  });
  dialog.addEventListener('keydown', (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (['ArrowRight', 'PageDown', 'ArrowLeft', 'PageUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      if (event.key === 'Home') showSlide(0);
      else if (event.key === 'End') showSlide(slides.length - 1);
      else showSlide(index + (['ArrowRight', 'PageDown'].includes(event.key) ? 1 : -1));
    } else if (event.code === 'Space') {
      event.preventDefault(); togglePlayback();
    }
  });
})();
