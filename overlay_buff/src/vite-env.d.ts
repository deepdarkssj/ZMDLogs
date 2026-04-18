/// <reference types="vite/client" />

declare module '*.json?raw' {
  const content: string;
  export default content;
}
