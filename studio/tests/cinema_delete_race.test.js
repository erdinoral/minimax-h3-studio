const fs = require('fs');
const assert = require('node:assert/strict');

const source = fs.readFileSync('studio/static/app.js', 'utf8');

assert.match(source, /cinemaAssetVersions/, 'Asset-level versioning must be present so stale patch responses cannot resurrect deleted cards.');
assert.match(source, /nextCinemaAssetVersion|patchCinemaAsset\(kind, id, fields\)/, 'Patch writes must be version-checked before mutating state.');
assert.match(source, /abortCinemaSaves\(/, 'Cinema save race guard must stay in place.');
assert.match(source, /cinemaDelegate\("cinema-creatures", "creature"\)/, 'Creature cards must receive image zoom/delete click handlers.');
assert.match(source, /\/api\/cinema\/creature\/\$\{encodeURIComponent\(aid\)\}/, 'Creature image edits must target the creature endpoint.');

console.log('Cinema deletion stale-response guard present.');
