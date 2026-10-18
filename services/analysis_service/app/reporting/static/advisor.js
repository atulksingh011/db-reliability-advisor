// Keep native form validation and same-origin actions; enhance only feedback UX.
document.querySelectorAll('[data-analysis-form]').forEach(function (form) {
  form.addEventListener('submit', function (event) {
    if (form.dataset.submitting) { event.preventDefault(); return; }
    form.dataset.submitting = 'true';
    document.querySelectorAll('[data-analysis-form] button').forEach(function (button) {
      button.disabled = true;
    });
    form.setAttribute('aria-busy', 'true');
    form.querySelector('button[type="submit"]').textContent = 'Running analysis…';
  });
});
// Restore native forms when returning through the browser's back/forward cache.
window.addEventListener('pageshow', function (event) { if (event.persisted) window.location.reload(); });

document.querySelectorAll('.copy-query').forEach(function (button) {
  button.addEventListener('click', async function () {
    var status = button.nextElementSibling;
    try {
      await navigator.clipboard.writeText(button.dataset.query);
      status.textContent = 'Copied';
    } catch (_) { status.textContent = 'Copy unavailable — select and copy the query above.'; }
  });
});

var feedback = document.querySelector('.feedback-form');
if (feedback) feedback.addEventListener('submit', async function (event) {
  event.preventDefault();
  if (feedback.dataset.submitting) return;
  feedback.dataset.submitting = 'true';
  var button = feedback.querySelector('button[type="submit"]');
  var status = feedback.querySelector('.feedback-status');
  button.disabled = true;
  button.textContent = 'Submitting…';
  status.textContent = '';
  try {
    var data = Object.fromEntries(new FormData(feedback));
    data.comment = data.comment || null;
    var response = await fetch(feedback.action, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error('Feedback was not accepted.');
    status.textContent = 'Feedback recorded. Thank you.';
    button.textContent = 'Submitted';
    feedback.querySelectorAll('input, textarea').forEach(function (input) { input.disabled = true; });
  } catch (_) {
    // A lost response can still mean a committed write; avoid an automatic retry.
    status.textContent = 'Could not confirm feedback. Check your connection before trying again.';
    button.disabled = false;
    button.textContent = 'Submit feedback';
    delete feedback.dataset.submitting;
  }
});
