import '@fontsource-variable/literata/opsz.css';
import '@fontsource-variable/literata/opsz-italic.css';
import '@fontsource-variable/instrument-sans/wght.css';
import { mount } from 'svelte';
import { registerSW } from 'virtual:pwa-register';
import App from './App.svelte';
import './app.css';

// The service worker opens the app, and the pictures already fetched, with the Pi out of reach.
registerSW({ immediate: true });

export default mount(App, { target: document.getElementById('app')! });
