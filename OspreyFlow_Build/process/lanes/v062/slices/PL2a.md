# Slice PL2a · PL2a · The Java runtime's NOTICE and source offer travel in the Conduit image (C020, ADR-147 Amendment 2)

- **Build id:** PL2a (the Java half of the plan's PL2; the connection-limit half is PL2b)
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing
- **Status of this brief:** written by the conductor on 20 November 2026 under the owner's word of the same day ("the Java notice in
  the image, with a test. Start it"), from a read-only scout of the same day. The choices below are the conductor's; the owner is
  told afterwards.

## What

`OspreyFlow_Core/services/api/Dockerfile` builds a Java runtime for the Conduit (stage `java`: `eclipse-temurin:21-jdk`, a `jlink`
runtime at `/opt/jre`, copied into the `runtime-included` stage as `/opt/java`, licence label `GPL-2.0-only WITH
Classpath-exception-2.0`, version `21.0.13+9`). The specification says the image's NOTICE and source offer are "a release step"
(`OspreyFlow_Build/spec/00_ARCHITECTURE.md` about lines 946-990; `spec/06_DECISIONS.md` ADR-147 Amendment 2 about lines
32914-32964, and about line 33061). The owner's ruling of 20 November 2026 puts the notice **in the image**. No NOTICE for the Java
runtime exists and no Dockerfile copies one into this image.

Choices, **settled by the conductor**:
1. **A committed file** `OspreyFlow_Core/services/api/JAVA_NOTICE` (plain text), copied by one `COPY` in the `runtime-included`
   stage to `/opt/java/NOTICE`. Not in `runtime-omitted` (the cloud-platform build carries no Java) and not in the final stage
   (`tests/test_conduit_image_java_licence.py` forbids a "java" line there). No new stage (the same test pins four stage names).
2. **Its content:** the runtime's name (Eclipse Temurin, from the OpenJDK) and its version exactly as the Dockerfile's version label
   (so the test can read the one from the other), its licence in the label's words, the Classpath exception, the source offer
   (Temurin's published source at the tag `jdk-21.0.13+9`, and the `jlink` line of the Dockerfile verbatim), and the bundled native
   libraries with their licences as the specification's table lists them (`spec/00_ARCHITECTURE.md` about lines 970-986). The
   licence texts themselves are **not** copied into the repository: the notice says that the GPL-2.0 text, the Classpath exception
   and the libraries' notices are in `/opt/java/legal` of the same image (the `jlink` runtime carries that tree; verify in the
   Dockerfile that the copy of `/opt/jre` takes it, and say so in the notice only if it does). **Write no URL that is not already
   in the repository**, and write no address for the offer's contact: say in your report what the notice does not hold (the owner's).
3. **The specification first (rule 11):** a new `### ADR-147, Amendment 6` in `spec/06_DECISIONS.md` (the number is free; add its row to
   `spec/ADR_RESERVATIONS.md` in the same change, in the table's form, lane `v062 PL2a`), stating that the NOTICE and source offer
   for the Conduit's Java runtime are carried in the image at `/opt/java/NOTICE`, and that the release step that remains is the
   publication of the image itself. Bring the two sentences that call it "a release step" (`spec/00` section 7 and `spec/06`
   about line 33061) to the amendment, naming it. Nothing else in the specification changes.
4. The pulled vendor images with a JVM (ArcadeDB, OpenSearch) are third-party: their notices are the vendors', and this slice does not
   touch them.

Binding: process/CLAUDE.md rules 11, 12, 15; the 18 November ruling that the client's name stays only in the four keep-files (the
notice names no client); British English.

## Acceptance test

One new file, `OspreyFlow_Build/tests/test_conduit_image_java_notice.py`, pure (it reads the real Dockerfile and the real notice
file), each case shown **red first** against a planted violation in the shape the code meets at its real call site (rule 15: the
real Dockerfile text with one line removed or changed, not a hand-written approximation; parse with the same helper the neighbouring
test uses, `tools.licence_check._instructions` and its `_stage`):
- the `runtime-included` stage has exactly one `COPY` whose source is the notice file and whose destination is `/opt/java/NOTICE`
  (plant: delete that line);
- neither `runtime-omitted` nor the final stage copies it (plant: add it to each);
- the notice file exists, and names the runtime, the version and the licence **exactly as the Dockerfile's labels give them** (plant:
  change the version in a copy of the Dockerfile's label, and the licence in the notice);
- the notice holds the source offer: the tag derived from the label's version (`jdk-<version>`) and the `jlink` line as the Dockerfile
  has it (plant: a notice without the tag; a notice whose `jlink` line differs);
- every bundled library in the specification's table is named in the notice (read the list from the specification text, so a library
  added there and not here is red);
- the notice holds no client's name (use the check the line already has for the abbreviation if one is importable; otherwise assert on
  the four keep-files' rule by reading `OspreyFlow_Core/NOTICE` for how the product names its holder);
- the Dockerfile still passes `tests/test_conduit_image_java_licence.py` (run it in the checks).
State, in the file's header, which test would fail if the notice were dropped from the image (rule 12).

## Checks

Pure only. The **checks command** runs `tests/test_conduit_image_java_licence.py`, `tests/harness/test_dockerfiles_numeric_user.py`,
`tests/harness/test_service_inventory.py`, `tests/licence_check/test_java_runtime_check.py`,
`tests/licence_check/test_runtime_licences.py` and `tests/licence_check/test_own_licence_and_notice.py`, and the licence check. The
**acceptance command** runs the new file alone. The line adds every mapped pure test that scans a folder the slice changes (the
specification walkers among them).

## Out of scope

The publication of the image; the vendor images' notices; any change to the Java stage, the digest pin, the labels, the user or the
final stage; a source-offer address or contact (the owner's: say what is missing); PL2b (connection limits).
