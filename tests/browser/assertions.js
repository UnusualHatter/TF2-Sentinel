/* Assertions run inside a real browser against the real docs/index.html.
 *
 * tests/browser/run_browser_test.py serves docs/ and injects this file plus
 * a small recorder, then collects the result that gets posted back.
 */
'use strict';

(function () {
  var results = [];

  function check(name, condition, detail) {
    results.push({ name: name, ok: !!condition, detail: condition ? '' : String(detail || '') });
  }

  function rows() {
    return document.querySelectorAll('#rows tr.account-row');
  }

  function waitFor(predicate, timeout) {
    return new Promise(function (resolve, reject) {
      var deadline = Date.now() + (timeout || 15000);
      (function poll() {
        var value;
        try { value = predicate(); } catch (error) { value = false; }
        if (value) return resolve(value);
        if (Date.now() > deadline) return reject(new Error('timed out waiting'));
        setTimeout(poll, 50);
      }());
    });
  }

  // The other two pages share lib/sentinel-data.js. Loading each one in a frame
  // is enough to catch a page whose script threw before it rendered anything.
  function loadPage(url) {
    return new Promise(function (resolve) {
      var frame = document.createElement('iframe');
      frame.setAttribute('src', url);
      frame.style.cssText = 'position:absolute;left:-9999px;width:1200px;height:800px';
      frame.addEventListener('load', function () { resolve(frame.contentDocument); });
      document.body.appendChild(frame);
    }).then(function (doc) {
      return waitFor(function () {
        return doc.querySelectorAll('#rows tr').length ? doc : false;
      }, 20000);
    });
  }

  function typeSearch(text) {
    var input = document.getElementById('q');
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function report() {
    return fetch('/__results__', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results: results, requests: window.__requests })
    });
  }

  waitFor(function () { return rows().length > 0; }).then(function () {
    check('the account table renders a full page', rows().length === 50, rows().length + ' rows');

    var stats = document.getElementById('stats').textContent;
    check('the result bar reports a total', /\d[\d,]* total/.test(stats), stats);

    var update = document.getElementById('last-update').textContent;
    check('the database date comes from meta.json', !/—$/.test(update), update);

    // The table renders from the accounts bundle alone; the profile cache is
    // applied as soon as it arrives, which is what this waits for.
    return waitFor(function () {
      return document.getElementById('profile-update').textContent;
    }).then(runChecks, function () {
      check('the profile cache is applied to the rendered table', false, 'never arrived');
      return report();
    });
  }, function (error) {
    check('the account table renders a full page', false, error && error.message);
    report();
  });

  function runChecks() {
    check('the profile cache is applied to the rendered table', true);

    var avatars = document.querySelectorAll('#rows img.avatar');
    var allowed = /^(avatar-placeholder\.svg|https:\/\/avatars\.steamstatic\.com\/[0-9a-f]{40}_medium\.jpg)$/;
    var badAvatar = null;
    var fromSteam = 0;
    avatars.forEach(function (img) {
      var raw = img.getAttribute('src');
      if (!allowed.test(raw)) badAvatar = raw;
      if (raw.indexOf('https://') === 0) fromSteam += 1;
    });
    check('every avatar src is the placeholder or a Steam CDN URL', !badAvatar, badAvatar);
    check('most of the first page has a real avatar', fromSteam > 25, fromSteam + '/50');

    var eager = 0;
    avatars.forEach(function (img, at) {
      if (at < 8 && img.getAttribute('loading') === 'eager') eager += 1;
    });
    check('the first rows load eagerly and the rest lazily',
      eager === 8 && avatars[49].getAttribute('loading') === 'lazy', eager);

    var named = 0;
    document.querySelectorAll('#rows .player-name').forEach(function (span) {
      if (span.textContent && span.textContent !== 'Unknown') named += 1;
    });
    check('persona names from the profile cache are shown', named > 25, named + '/50');

    var links = document.querySelectorAll('#rows .profile-links a');
    check('profile links point at Steam and SteamHistory',
      /^https:\/\/steamcommunity\.com\/profiles\/7656119\d{10}\/$/.test(links[0].getAttribute('href'))
      && /^https:\/\/steamhistory\.net\/id\/7656119\d{10}$/.test(links[1].getAttribute('href')),
      links[0].getAttribute('href'));

    var first = rows()[0].querySelector('.steamid').textContent;
    var wanted = rows()[3].querySelector('.steamid').textContent;

    // pagination
    document.querySelector('#pager-top [data-page="next"]').click();
    return waitFor(function () {
      return rows().length && rows()[0].querySelector('.steamid').textContent !== first;
    }).then(function () {
      check('paging forward shows a different slice', true);
      var pager = document.getElementById('pager-top').textContent;
      check('the pager reports the new page', /Page 2 of/.test(pager), pager);
      document.querySelector('#pager-top [data-page="prev"]').click();
      return waitFor(function () {
        return rows().length && rows()[0].querySelector('.steamid').textContent === first;
      });
    }).then(function () {
      check('paging back returns to the first slice', true);

      // exact SteamID64 lookup
      typeSearch(wanted);
      return waitFor(function () { return rows().length === 1; }, 5000);
    }).then(function () {
      check('an exact SteamID64 search finds exactly one account',
        rows()[0].querySelector('.steamid').textContent === wanted);

      var accountId = Number(wanted.slice(7)) - 7960265728;
      typeSearch('https://steamcommunity.com/profiles/' + wanted + '/');
      return waitFor(function () { return rows().length === 1; }, 5000).then(function () {
        check('a pasted Steam profile link finds the account',
          rows()[0].querySelector('.steamid').textContent === wanted);
        typeSearch('[U:1:' + accountId + ']');
        return waitFor(function () { return rows().length === 1; }, 5000);
      }).then(function () {
        check('a Steam3 ID finds the account',
          rows()[0].querySelector('.steamid').textContent === wanted);
        typeSearch('STEAM_0:' + (accountId % 2) + ':' + Math.floor(accountId / 2));
        return waitFor(function () { return rows().length === 1; }, 5000);
      }).then(function () {
        check('a Steam2 ID finds the account',
          rows()[0].querySelector('.steamid').textContent === wanted);
        typeSearch('zzzznotinthedatabasezzzz');
        return waitFor(function () {
          return rows().length === 0
            && /^No matching/.test(document.getElementById('stats').textContent);
        }, 5000);
      });
    }).then(function () {
      check('a search with no matches reports that plainly', true);
      typeSearch('server ban');
      return waitFor(function () {
        return /matching/.test(document.getElementById('stats').textContent) && rows().length > 0;
      }, 8000);
    }).then(function () {
      check('a two-word query returns results', rows().length > 0);
      typeSearch('zzzznotinthedatabasezzzz');
      return waitFor(function () {
        return rows().length === 0 && /^No matching/.test(document.getElementById('stats').textContent);
      }, 5000);
    }).then(function () {
      check('a two-word query can still be narrowed to nothing', true);

      typeSearch('');
      return waitFor(function () { return rows().length === 50; }, 5000);
    }).then(function () {
      check('clearing the search restores the full list', true);

      // source expansion
      var expand = document.querySelector('#rows [data-expand]');
      check('rows with several sources offer to expand', !!expand);
      if (!expand) return null;
      expand.click();
      return waitFor(function () { return document.querySelector('#rows tr.detail-row'); }, 5000)
        .then(function () {
          var panel = document.querySelector('#rows .detail-panel');
          check('the detail panel lists the sources',
            panel.querySelectorAll('.source-list li').length > 1);
          var links = panel.querySelectorAll('a');
          var bad = null;
          links.forEach(function (a) {
            if (!/^https?:\/\//.test(a.getAttribute('href'))) bad = a.getAttribute('href');
          });
          check('every source link is a plain web link', !bad, bad);
          document.querySelector('#rows [data-expand]').click();
          return waitFor(function () { return !document.querySelector('#rows tr.detail-row'); }, 5000);
        }).then(function () {
          check('the detail panel closes again', true);
          return null;
        });
    }).then(function () {
      // broken avatar handling
      var img = document.querySelector('#rows img.avatar');
      img.src = 'https://avatars.steamstatic.com/' + '0'.repeat(40) + '_medium.jpg';
      return waitFor(function () {
        return img.getAttribute('src') === 'avatar-placeholder.svg';
      }, 10000).then(function () {
        check('a broken avatar falls back to the placeholder once', true);
        check('the fallback does not loop', img.dataset.fallback === '1');
      }, function () {
        check('a broken avatar falls back to the placeholder once', false,
          'still ' + img.getAttribute('src'));
      });
    }).then(function () {
      var external = window.__requests.filter(function (url) {
        return url.indexOf(location.origin) !== 0;
      });
      check('no request goes to a third-party proxy',
        !window.__requests.some(function (url) { return /allorigins/i.test(url); }),
        external.join(' '));
      var offSteam = external.filter(function (url) {
        return !/^https:\/\/avatars\.steamstatic\.com\/[0-9a-f]{40}_medium\.jpg$/.test(url);
      });
      check('the only third party the page talks to is the Steam avatar CDN',
        offSteam.length === 0, offSteam.join(' '));
      var dataFiles = window.__requests.filter(function (url) { return url.indexOf('/data/') !== -1; });
      check('startup reads at most four data files',
        dataFiles.length <= 4, dataFiles.join(' '));
      check('localStorage no longer holds the retired avatar cache',
        window.localStorage.getItem('sentinel_avatar_cache_v1') === null);
    }).then(function () {
      // The invariant is per render, not per session: turning one page must
      // never warm more than the one page that comes after it.
      var mark = window.__requests.length;
      document.querySelector('#pager-top [data-page="next"]').click();
      return new Promise(function (resolve) { setTimeout(resolve, 3000); }).then(function () {
        var added = window.__requests.length - mark;
        check('turning a page warms at most one page of avatars', added <= 50, added + ' requests');
      });
    }).then(function () {
      return loadPage('sources.html').then(function (doc) {
        check('the source catalog page renders', doc.querySelectorAll('#rows tr').length > 1,
          doc.querySelectorAll('#rows tr').length);
        check('the source catalog counts what it loaded',
          /registered sources$/.test(doc.getElementById('stats').textContent),
          doc.getElementById('stats').textContent);
        var bad = null;
        doc.querySelectorAll('#rows a').forEach(function (a) {
          if (!/^https?:\/\//.test(a.getAttribute('href'))) bad = a.getAttribute('href');
        });
        check('every catalog link is a plain web link', !bad, bad);
      }, function (error) {
        check('the source catalog page renders', false, error && error.message);
      });
    }).then(function () {
      return loadPage('servers.html').then(function (doc) {
        check('the servers page renders', doc.querySelectorAll('#rows tr').length > 1,
          doc.querySelectorAll('#rows tr').length);
        check('the servers page shows the database date',
          !/—$/.test(doc.getElementById('last-update').textContent),
          doc.getElementById('last-update').textContent);
        var bad = null;
        doc.querySelectorAll('#rows a').forEach(function (a) {
          if (!/^https?:\/\//.test(a.getAttribute('href'))) bad = a.getAttribute('href');
        });
        check('every moderation link is a plain web link', !bad, bad);
      }, function (error) {
        check('the servers page renders', false, error && error.message);
      });
    }).then(report, function (error) {
      check('the assertion run finished', false, error && error.message);
      return report();
    });
  }
}());
