/** Reusable Card component. */

import React from "react";

/**
 * Card component.
 * @param {Object} props - Component props
 * @param {React.ReactNode} props.children - Card content
 * @param {string} props.className - Additional CSS classes
 */
export function Card({ children, className = "", ...props }) {
  const baseClasses = "bg-white rounded-2xl shadow-lg border border-gray-100";
  const classes = `${baseClasses} ${className}`;

  return (
    <div className={classes} {...props}>
      {children}
    </div>
  );
}

