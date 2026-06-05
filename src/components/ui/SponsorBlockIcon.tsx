interface SponsorBlockIconProps {
  className?: string;
}

/**
 * SponsorBlock brand mark (shield + play), traced from the official logo
 * (github.com/ajayyy/SponsorBlock). Red shield with a white play triangle.
 */
export function SponsorBlockIcon({ className }: SponsorBlockIconProps) {
  return (
    <svg
      viewBox="0 0 565.15 568"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {/* Shield outer ring */}
      <path
        fill="#e02d2d"
        d="M282.58,568a65,65,0,0,1-34.14-9.66C95.41,463.94,2.54,300.46,0,121A64.91,64.91,0,0,1,34,62.91a522.56,522.56,0,0,1,497.16,0,64.91,64.91,0,0,1,34,58.12c-2.53,179.43-95.4,342.91-248.42,437.3A65,65,0,0,1,282.58,568Zm0-548.31A502.24,502.24,0,0,0,43.4,80.22a45.27,45.27,0,0,0-23.7,40.53c2.44,172.67,91.81,330,239.07,420.83a46.19,46.19,0,0,0,47.61,0C453.64,450.73,543,293.42,545.45,120.75a45.26,45.26,0,0,0-23.7-40.54A502.26,502.26,0,0,0,282.58,19.69Z"
      />
      {/* Shield body */}
      <path
        fill="#e02d2d"
        d="M284.71,42.69A479.9,479.9,0,0,0,54.37,100.42,22.53,22.53,0,0,0,42.67,120.42C45.07,290.26,135.67,438.64,270.83,522a22.48,22.48,0,0,0,23.49,0C429.48,438.64,520.08,290.26,522.48,120.42a22.53,22.53,0,0,0-11.7-20A479.9,479.9,0,0,0,284.71,42.69Z"
      />
      {/* Play triangle */}
      <path fill="#fff" d="M220.41,145.74,411.28,255.94,220.41,366.14Z" />
    </svg>
  );
}
