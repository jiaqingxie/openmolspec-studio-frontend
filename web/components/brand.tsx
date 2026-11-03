export function MolspecMark({
  className = "",
  size = 48,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <img
      className={`molspec-mark ${className}`}
      src="/molspec-mark.svg"
      alt=""
      width={size}
      height={size}
      draggable={false}
    />
  );
}
