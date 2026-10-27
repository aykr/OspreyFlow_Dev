/** ADR-130 Amendment 2: what every surface that would list an element's sources says instead, when
 * the element belongs to a dataset the case does not read and the Conduit has sent it with
 * `provenance.sources_withheld` set. Never "No sources recorded": there are some, and they are not
 * this case's to see. */
export const SOURCES_WITHHELD_TEXT = "Its sources are in data this case does not read";
