/**
 * Deep equality and diff utilities for production-grade form state tracking.
 */

export function deepEqual(a: any, b: any): boolean {
  if (a === b) return true;

  if (a === null || a === undefined || b === null || b === undefined) {
    return a === b;
  }

  if (typeof a !== typeof b) return false;

  if (typeof a !== "object") {
    return a === b;
  }

  // Array comparison
  if (Array.isArray(a)) {
    if (!Array.isArray(b)) return false;
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) return false;
    }
    return true;
  }

  if (Array.isArray(b)) return false;

  // Date comparison
  if (a instanceof Date && b instanceof Date) {
    return a.getTime() === b.getTime();
  }

  // Plain Object comparison
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);

  // Ignore undefined keys when counting
  const nonUndefinedA = keysA.filter((k) => a[k] !== undefined);
  const nonUndefinedB = keysB.filter((k) => b[k] !== undefined);

  if (nonUndefinedA.length !== nonUndefinedB.length) return false;

  for (const key of nonUndefinedA) {
    if (!deepEqual(a[key], b[key])) return false;
  }

  return true;
}

export function cloneDeep<T>(obj: T): T {
  if (obj === null || typeof obj !== "object") {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map((item) => cloneDeep(item)) as unknown as T;
  }

  if (obj instanceof Date) {
    return new Date(obj.getTime()) as unknown as T;
  }

  const copy: Record<string, any> = {};
  for (const key of Object.keys(obj as Record<string, any>)) {
    const val = (obj as Record<string, any>)[key];
    if (val !== undefined) {
      copy[key] = cloneDeep(val);
    }
  }

  return copy as T;
}

/**
 * Returns a record of field keys mapped to boolean indicating whether the field differs between original and current.
 */
export function getDirtyFields(
  original: Record<string, any> = {},
  current: Record<string, any> = {}
): Record<string, boolean> {
  const dirtyMap: Record<string, boolean> = {};
  const allKeys = new Set([...Object.keys(original), ...Object.keys(current)]);

  for (const key of allKeys) {
    const origVal = original[key];
    const currVal = current[key];

    if (!deepEqual(origVal, currVal)) {
      dirtyMap[key] = true;
    }
  }

  return dirtyMap;
}

/**
 * Computes a partial diff object containing ONLY the key-value pairs from current that differ from original.
 */
export function getDiffPayload(
  original: Record<string, any> = {},
  current: Record<string, any> = {}
): Record<string, any> {
  const diff: Record<string, any> = {};
  const dirtyMap = getDirtyFields(original, current);

  for (const key of Object.keys(dirtyMap)) {
    if (dirtyMap[key]) {
      diff[key] = current[key];
    }
  }

  return diff;
}
