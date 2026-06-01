/**
 * Decorative color glows behind the app content.
 *
 * Uses `radial-gradient` backgrounds rather than a blurred element
 * (`filter: blur`): WebKitGTK (the Tauri webview) fails to repaint scrolled
 * content sitting over a large CSS blur, leaving ghost/duplicated text. A
 * radial gradient gives the same soft glow without triggering that bug.
 */
export function BackgroundGlow() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      <div
        className="absolute top-[-160px] left-[8%] size-[460px] rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(124,58,237,0.22), transparent 70%)",
        }}
      />
      <div
        className="absolute bottom-[-180px] right-[4%] size-[520px] rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(37,99,235,0.22), transparent 70%)",
        }}
      />
    </div>
  );
}
