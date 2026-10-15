# The Enron email corpus: terms and privacy

**This is real data**: the email of about 150 people who worked at Enron, released into the public
record during the US Federal Energy Regulatory Commission's investigation, and prepared and distributed
by Carnegie Mellon University.

- **Source:** https://www.cs.cmu.edu/~enron/ — the May 7, 2015 version, `enron_mail_20150507.tar.gz`
- **Licence:** **none is stated.** The source page says: "I am distributing this dataset as a resource
  for researchers who are interested in improving current email tools".
- **Privacy:** the source page asks: "please be sensitive to the privacy of the people involved".
  Some messages were deleted at the request of affected employees; earlier versions are no longer
  distributed, and a copy of one should be replaced by this version.

## What OspreyFlow does and does not do

- OspreyFlow never carries this corpus: not in its repository, a release, a bundle, an image or its
  tests. You download it from the source page yourself.
- `ospreyflow demo add enron --file <path>` checks the file is exactly the May 7, 2015 version, shows
  you what it is, and loads it only after you accept. The acceptance is kept beside the corpus on your
  machine.
- Whether you may process it is for you and your organisation to decide: it is personal data, and you
  need your own lawful basis to process it. Use it for research and demonstration, and keep it on the
  machine you loaded it on.
