/* KISA Bunny Stream admin upload. No Bunny API keys enter the browser.
   Uses TUS 1.0 direct from browser to Bunny; works without an external JS library. */
(() => {
  'use strict';
  const form = document.getElementById('kisa-bunny-upload');
  if (!form) return;
  const button = document.getElementById('bunny-upload-button');
  const meter = document.getElementById('bunny-meter');
  const message = document.getElementById('bunny-upload-message');
  const statusButton = document.getElementById('bunny-check-status');
  const previewButton = document.getElementById('bunny-preview-video');
  const csrf = form.querySelector('[name="csrf"]').value;
  const episodeSelect = form.querySelector('[name="episode"]');
  const fileInput = form.querySelector('[name="video"]');
  const MAX_FILE = 1024 * 1024 * 1024; // 1 GiB - admin-focused limit
  const CHUNK = 8 * 1024 * 1024;
  const retryDelays = [0, 1500, 3500, 7000, 14000];

  function show(text, isError = false) {
    message.textContent = text;
    message.style.color = isError ? '#ff92a7' : '#a6eac8';
  }
  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options });
    if (!response.ok) {
      let problem = `${response.status} ${response.statusText}`;
      try { const err = await response.json(); problem = err.detail || problem; } catch (_) {}
      throw new Error(String(problem));
    }
    return response.json();
  }
  function headerFields(ticket) {
    return {
      'Tus-Resumable': '1.0.0',
      'AuthorizationSignature': ticket.signature,
      'AuthorizationExpire': String(ticket.expires),
      'VideoId': ticket.video_id,
      'LibraryId': String(ticket.library_id)
    };
  }
  function base64(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = '';
    for (const part of bytes) binary += String.fromCharCode(part);
    return btoa(binary);
  }
  async function tusOffset(url, headers) {
    const response = await fetch(url, { method: 'HEAD', headers, mode: 'cors', cache: 'no-store' });
    if (!response.ok) throw new Error(`Cannot resume upload (HEAD ${response.status})`);
    const raw = response.headers.get('Upload-Offset');
    const offset = Number(raw);
    if (raw === null || !Number.isSafeInteger(offset) || offset < 0) {
      throw new Error('Missing valid Upload-Offset header from Bunny. Check CORS.');
    }
    return offset;
  }
  function uploadStorageKey(episode, file, videoId) {
    return `kisa:tus:${episode}:${videoId}:${file.name}:${file.size}:${file.lastModified}`;
  }
  async function uploadFile(file, ticket, episode) {
    const common = headerFields(ticket);
    const key = uploadStorageKey(episode, file, ticket.video_id);
    let location = sessionStorage.getItem(key);
    let offset = 0;
    if (location) {
      try {
        // Never fetch arbitrary URLs from session storage.
        if (new URL(location).origin !== 'https://video.bunnycdn.com') throw new Error('Unexpected upload origin');
        offset = await tusOffset(location, common);
      } catch (_) {
        location = null;
        sessionStorage.removeItem(key);
      }
    }
    if (!location) {
      show('Preparing a secure, resumable upload…');
      const metadata = [
        `filename ${base64(file.name)}`,
        `filetype ${base64(file.type || 'video/mp4')}`,
        `title ${base64(episode + ' / ' + file.name)}`
      ].join(',');
      const response = await fetch(ticket.tus_endpoint, {
        method: 'POST', mode: 'cors', cache: 'no-store',
        headers: { ...common, 'Upload-Length': String(file.size), 'Upload-Metadata': metadata }
      });
      if (!response.ok) throw new Error(`Bunny refused upload creation (HTTP ${response.status})`);
      const nextLocation = response.headers.get('Location');
      if (!nextLocation) throw new Error('Bunny did not return Location; check exposed CORS headers.');
      location = new URL(nextLocation, ticket.tus_endpoint).href;
      if (new URL(location).origin !== 'https://video.bunnycdn.com') {
        throw new Error('Unexpected Bunny upload URL origin');
      }
      sessionStorage.setItem(key, location);
    }
    if (offset > file.size) throw new Error('Unexpected upload offset. Restart the upload.');
    while (offset < file.size) {
      const end = Math.min(offset + CHUNK, file.size);
      const chunk = file.slice(offset, end);
      let lastError;
      for (let attempt = 0; attempt < retryDelays.length; attempt++) {
        if (retryDelays[attempt]) await new Promise(r => setTimeout(r, retryDelays[attempt]));
        try {
          const response = await fetch(location, {
            method: 'PATCH', mode: 'cors', cache: 'no-store',
            headers: { ...common,
              'Content-Type': 'application/offset+octet-stream',
              'Upload-Offset': String(offset)
            }, body: chunk
          });
          if (!response.ok) throw new Error(`Bunny rejected upload chunk (HTTP ${response.status})`);
          const next = Number(response.headers.get('Upload-Offset'));
          // An absent offset header is not sufficient proof of progress.
          if (!Number.isSafeInteger(next) || next <= offset || next > file.size) {
            throw new Error('Invalid upload offset response from Bunny');
          }
          offset = next;
          lastError = null;
          break;
        } catch (error) {
          lastError = error;
          try { offset = await tusOffset(location, common); } catch (_) {}
          if (offset > end) { lastError = new Error('Upload offset mismatch'); break; }
          // Server may already have accepted part/all of the chunk.
          // Start the next chunk at its authoritative offset.
          if (offset > end - chunk.size) { lastError = null; break; }
        }
      }
      if (lastError) throw lastError;
      meter.value = Math.round(offset / file.size * 100);
      show(`Uploading ${meter.value}% — ${Math.round(offset / 1024 / 1024)} MB of ${Math.round(file.size / 1024 / 1024)} MB`);
    }
    sessionStorage.removeItem(key);
  }
  async function checkStatus() {
    const episode = episodeSelect.value;
    if (!episode) return show('Choose an episode first.', true);
    try {
      const state = await jsonRequest('/admin/videos/bunny/status/' + encodeURIComponent(episode));
      if (state.ready) show('Video READY. Use Publish Episode below to make it visible.');
      else show(`Bunny processing status: ${state.status}; encoding: ${state.encode_progress ?? 0}%. Recheck in 20 seconds.`);
    } catch (error) { show(error.message, true); }
  }
  statusButton.addEventListener('click', checkStatus);
  previewButton.addEventListener('click', () => {
    const episode = episodeSelect.value;
    if (!episode) return show('Choose an episode first.', true);
    window.open('/admin/videos/bunny/preview/' + encodeURIComponent(episode), '_blank', 'noopener');
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const episode = episodeSelect.value;
    const file = fileInput.files[0];
    if (!episode || !file) return show('Choose an episode and MP4.', true);
    if (!file.name.toLowerCase().endsWith('.mp4') || file.size < 1 || file.size > MAX_FILE) {
      return show('Choose an MP4 between 1 byte and 1 GiB.', true);
    }
    button.disabled = true;
    meter.value = 0;
    try {
      const ticket = await jsonRequest('/admin/videos/bunny/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ episode_id: episode, filename: file.name, size_bytes: file.size })
      });
      await uploadFile(file, ticket, episode);
      show('Upload complete! Bunny is transcoding the video. Wait until READY before publishing.');
      await checkStatus();
    } catch (error) {
      show('Upload interrupted: ' + error.message + '. Select the same file and click Upload again to resume.', true);
    } finally {
      button.disabled = false;
    }
  });
})();
