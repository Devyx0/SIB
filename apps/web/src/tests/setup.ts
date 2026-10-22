import '@testing-library/jest-dom';

// jsdom has no scrolling; pages call window.scrollTo when they open.
window.scrollTo = () => {};
