/* Revision-aware refreshes, independent of DOM rendering and browser globals. */
(function (root, factory) {
  const updates = factory();
  if (typeof module === 'object' && module.exports) module.exports = updates;
  else root.JobUpdates = updates;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function createLoader(api) {
    const pending = new Map();
    return function load(id, previous) {
      if (pending.has(id)) return pending.get(id);
      const request = (async () => {
        const status = await api(`/api/jobs/${id}/status`);
        if (previous && status.payload_revision === previous.payload_revision) {
          return {...previous, ...status};
        }
        return api(`/api/jobs/${id}`);
      })();
      pending.set(id, request);
      // Both success and failure release the slot without creating an unhandled rejection.
      request.then(() => pending.delete(id), () => pending.delete(id));
      return request;
    };
  }

  function shouldApply(selectedId, current, incoming) {
    return Boolean(incoming && incoming.id === selectedId &&
      (!current || current.id !== incoming.id || incoming.revision > current.revision));
  }

  return {createLoader, shouldApply};
});
