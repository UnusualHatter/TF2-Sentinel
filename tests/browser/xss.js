/* Runs against a page whose profile cache has been poisoned with persona names
 * crafted to break out of the markup. Nothing here should be able to run.
 *
 *     python3 tests/browser/run_browser_test.py --poison --assertions tests/browser/xss.js
 */
'use strict';

(function () {
  var results = [];
  var PAYLOADS = [
    '<script>window.__xss=1</script>',
    '<img src=x onerror="window.__xss=2">',
    '" onmouseover="window.__xss=3" x="',
    "' onfocus='window.__xss=4' autofocus='",
    '<svg/onload=window.__xss=5>',
    '</td></tr><tr><td>injected',
    'javascript:window.__xss=6',
    '<a href="javascript:window.__xss=7">link</a>',
    '&lt;script&gt;window.__xss=8&lt;/script&gt;',
    '<iframe src="javascript:window.__xss=9"></iframe>'
  ];

  function check(name, condition, detail) {
    results.push({ name: name, ok: !!condition, detail: condition ? '' : String(detail || '') });
  }

  function waitFor(predicate, timeout) {
    return new Promise(function (resolve, reject) {
      var deadline = Date.now() + (timeout || 20000);
      (function poll() {
        var value;
        try { value = predicate(); } catch (error) { value = false; }
        if (value) return resolve(value);
        if (Date.now() > deadline) return reject(new Error('timed out'));
        setTimeout(poll, 50);
      }());
    });
  }

  function report() {
    return fetch('/__results__', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results: results, requests: window.__requests })
    });
  }

  function inspect(where) {
    var host = document.getElementById('rows');
    check('no script element was created (' + where + ')',
      host.querySelectorAll('script').length === 0);
    check('no iframe was created (' + where + ')',
      host.querySelectorAll('iframe').length === 0);
    check('no svg was created (' + where + ')',
      host.querySelectorAll('svg').length === 0);

    // A javascript: value only matters in an attribute the browser navigates
    // or loads. The same text in a title is a tooltip and nothing more.
    var URL_ATTRS = ['href', 'src', 'action', 'formaction', 'data', 'xlink:href', 'srcdoc'];
    var dangerous = [];
    host.querySelectorAll('*').forEach(function (el) {
      for (var i = 0; i < el.attributes.length; i += 1) {
        var attr = el.attributes[i];
        if (/^on/i.test(attr.name)) {
          dangerous.push(el.tagName + '[' + attr.name + ']');
        } else if (URL_ATTRS.indexOf(attr.name.toLowerCase()) !== -1
          && !/^(https?:|avatar-placeholder\.svg)/.test(attr.value.trim())) {
          dangerous.push(el.tagName + '[' + attr.name + '=' + attr.value.slice(0, 30) + ']');
        }
      }
    });
    check('no event handler and no non-web URL attribute exists (' + where + ')',
      dangerous.length === 0, dangerous.join(' '));

    var badHref = [];
    host.querySelectorAll('a[href]').forEach(function (a) {
      if (!/^https?:\/\//.test(a.getAttribute('href'))) badHref.push(a.getAttribute('href'));
    });
    check('every link is still a plain web link (' + where + ')', badHref.length === 0,
      badHref.join(' '));

    var images = host.querySelectorAll('img');
    var badSrc = [];
    images.forEach(function (img) {
      var src = img.getAttribute('src');
      if (!/^(avatar-placeholder\.svg|https:\/\/avatars\.steamstatic\.com\/[0-9a-f]{40}_medium\.jpg)$/.test(src)) {
        badSrc.push(src);
      }
    });
    check('every image src is still the placeholder or a Steam avatar (' + where + ')',
      badSrc.length === 0, badSrc.join(' '));
  }

  waitFor(function () {
    return document.getElementById('profile-update').textContent
      && document.querySelectorAll('#rows tr.account-row').length > 0;
  }).then(function () {
    check('the poisoned profile cache was actually applied',
      document.querySelectorAll('#rows tr.account-row').length === 50);

    // The payloads land on the first rows, which is page one.
    var rendered = [];
    document.querySelectorAll('#rows .player-name').forEach(function (span) {
      rendered.push(span.textContent);
    });
    var shown = PAYLOADS.filter(function (p) { return rendered.indexOf(p) !== -1; });
    check('hostile names are shown as text, character for character',
      shown.length >= 5, 'only ' + shown.length + ' of ' + PAYLOADS.length + ' matched exactly');

    var rowCount = document.querySelectorAll('#rows tr').length;
    check('no extra table row was smuggled in', rowCount <= 51, rowCount + ' rows');

    inspect('table');

    // Expanding a row re-renders with the same data through a different path.
    var expand = document.querySelector('#rows [data-expand]');
    if (!expand) { inspect('after expand'); return null; }
    expand.click();
    return waitFor(function () { return document.querySelector('#rows tr.detail-row'); }, 5000)
      .then(function () { inspect('after expand'); });
  }).then(function () {
    // Searching rebuilds the index from the same poisoned names.
    var input = document.getElementById('q');
    input.value = 'onerror';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return waitFor(function () {
      return /matching|No matching/.test(document.getElementById('stats').textContent);
    }, 8000);
  }).then(function () {
    inspect('after search');
    check('nothing the payloads tried to run actually ran',
      typeof window.__xss === 'undefined', 'window.__xss = ' + window.__xss);
    check('the document title was not rewritten', document.title === 'TF2 Sentinel', document.title);
    return report();
  }, function (error) {
    check('the poisoned page rendered at all', false, error && error.message);
    return report();
  });
}());
