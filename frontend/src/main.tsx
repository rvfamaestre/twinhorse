import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import { App } from "./App";
import "./styles.css";

// Sin StrictMode: el doble montaje de desarrollo hace que las etiquetas <Html> de drei avisen en consola.
createRoot(document.getElementById("root")!).render(<App />);
