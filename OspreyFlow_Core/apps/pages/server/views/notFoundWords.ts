/**
 * The words of a path nothing serves (the service's own 404). One place, so that a page which answers a refusal as "not there"
 * (the Admin People page, slice AD3a: a person who may not read it is told what they are told for a path that does not exist) says
 * exactly what the service says for one, byte for byte: the owner's ruling of 24 November 2026, "a non-viewer gets 404, the same as
 * a missing thing". `app.ts` renders it as the last thing it does, and a page renders it with the same template.
 */
export const NOT_FOUND = { title: "Page not found", message: "That page could not be found." } as const;
