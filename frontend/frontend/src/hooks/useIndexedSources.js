import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { INDEXED_SOURCES } from "@/lib/sources";

// One /v1/sources request per page load, shared by every component.
let cached = api.demo ? INDEXED_SOURCES : null;
let pending = null;

function load() {
  if (!pending) {
    pending = api.getSources().then(
      (list) => {
        cached = list;
        return list;
      },
      () => {
        pending = null; // retry on the next mount
        return [];
      },
    );
  }
  return pending;
}

export function useIndexedSources() {
  const [sources, setSources] = useState(cached || []);
  useEffect(() => {
    if (cached) return undefined;
    let alive = true;
    load().then((list) => { if (alive) setSources(list); });
    return () => { alive = false; };
  }, []);
  return sources;
}
