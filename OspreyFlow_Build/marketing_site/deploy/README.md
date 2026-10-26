# OspreyFlow website: going live

`index.html` is the whole site in one file: fonts, screenshots, the Solirius Reply logo and the animation are all inside it. The video carousel's first slide loads `intro-video.html`, the animated overview, so keep that file next to `index.html`.

## Option A: GitHub Pages (recommended)

1. On GitHub, create a public repository, for example `ospreyflow-site`. Alternatively, use the existing `aykr/OspreyFlow` repository and put the files in a `docs/` folder.
2. Upload `index.html`, `intro-video.html` and `.nojekyll` to the root of the repository, or to `docs/`, and commit.
3. Go to **Settings → Pages**. Under *Build and deployment*, choose **Deploy from a branch**, then select branch `main` and folder `/ (root)` or `/docs`. Click **Save**.
4. After a minute or two the site is live at `https://<your-account>.github.io/<repository>/`. The address is shown at the top of the Pages settings.
5. Optional, to use your own domain: in **Settings → Pages → Custom domain**, enter it, for example `ospreyflow.solirius.com`. Then add a `CNAME` DNS record pointing to `<your-account>.github.io`, and tick **Enforce HTTPS** once it is available.

To update the site later, replace `index.html` in the repository and commit. Pages republishes automatically.

## Option B: Google Sites

Google Sites can't host an HTML file directly. It shows external pages in an embed frame. The most reliable way is to publish on GitHub Pages first (Option A), then embed that address:

1. Open your Google Site and go to **Insert → Embed → By URL**.
2. Paste the GitHub Pages address and choose **Whole page**. Click **Insert**.
3. Drag the embed's handles to the full width of the section and make it tall. The site scrolls inside the frame.
4. Click **Publish**.

Alternatively, add a menu item or a button on Google Sites that links to the GitHub Pages address and opens it in a new tab.

Pasting the file into **Insert → Embed → Embed code** isn't recommended. The file is about 2.4 MB, which is larger than that box reliably accepts.

## Adding the introduction video later

The page shows a placeholder until a video address is set.

1. Upload the video to YouTube or Vimeo and copy its **embed** URL, for example `https://www.youtube.com/embed/VIDEO_ID`.
2. In the design project, open `OspreyFlow Site.dc.html`, set the `videoUrl` setting to that URL, and export the standalone HTML again.
3. Replace `index.html` in the repository with the new export.

The animated placeholder video (`OspreyFlow Intro Video.dc.html`) can be exported as MP4 from **Share → Export → Video** in the design project, then uploaded the same way.

## Checklist before going live

- The GitHub link in the page points to `https://github.com/aykr/OspreyFlow`. If the public repository lives elsewhere, change the `repoUrl` setting and export again.
- The product screenshots are from the current product decks. Replace them with fresh captures when the restyled workspace is released.
- Confirm that the Solirius Reply logo and the team photo are cleared for use on this site.
