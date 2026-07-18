# Privacy Policy — Send to Yoink

_Last updated: 18 July 2026_

**Send to Yoink collects no data.** It has no servers, no analytics, no tracking and no
accounts. Nothing you do with it is sent to the developer or to any third party.

## What the extension does

When you click **“Download with Yoink”** in the right-click menu (or the toolbar
button), the extension takes the URL of the page you are on — or of the link you
right-clicked — and opens a `yoink://download?url=<encoded URL>` link. Your operating
system hands that link to the **Yoink desktop application installed on your own
computer**, which then shows a download preview.

The extension itself never downloads, stores or uploads anything. It is only a bridge
between your browser and your own local application.

## Data handling

- **No collection.** The URL is read only at the moment you activate the extension, and
  is passed straight to your local Yoink app. It is not stored, logged or retained.
- **No transmission off your device.** The URL never leaves your computer: it goes from
  the browser to a local application through the operating system's protocol handler.
  There is no network request to the developer or to anyone else.
- **No page content.** The extension does not read, inject or modify the content of the
  pages you visit.
- **No tracking.** No analytics, cookies, fingerprinting or advertising identifiers.
- **No selling or sharing.** As no data is collected, none is sold, shared or
  transferred to third parties.

## Permissions and why they are needed

| Permission | Why |
| --- | --- |
| `contextMenus` | To add the single “Download with Yoink” item to the right-click menu. |
| `activeTab` | To read the URL of the tab you explicitly invoked the extension on. |
| `scripting` | To open the `yoink://` link from that tab so your local app receives it. |

No host permissions are requested, so the extension has no standing access to any site.

## Changes

Any future change to this policy will be published in this file, in the extension's
repository.

## Contact

Questions or issues: <https://github.com/ayozetr/yoink-app/issues>
