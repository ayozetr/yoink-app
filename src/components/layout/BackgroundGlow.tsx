/** Decorative blurred color blobs behind the app content. */
export function BackgroundGlow() {
  return (
    <div className="absolute inset-0 pointer-events-none">
      <div className="absolute top-[-100px] left-[15%] h-72 w-72 rounded-full bg-violet-600/20 blur-3xl" />
      <div className="absolute bottom-[-120px] right-[10%] h-80 w-80 rounded-full bg-blue-600/20 blur-3xl" />
    </div>
  );
}
