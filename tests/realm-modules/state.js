// Same URI in each realm: a fresh module graph must execute this again.
export const owner = globalThis;
export const token = {};
export class View {}
globalThis.moduleExecutions = (globalThis.moduleExecutions ?? 0) + 1;
