import './navigation.css';

export type NavigationActions = {
  goHome: () => void;
};

export default function NavigationControls({ navigation }: { navigation: NavigationActions }) {
  return (
    <nav className="page-navigation" aria-label="Page navigation">
      <button type="button" className="page-home-button" aria-label="Home" title="Home" onClick={navigation.goHome}>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m3.5 10 8.5-7 8.5 7M5.5 8.5v11a1 1 0 0 0 1 1H10v-6h4v6h3.5a1 1 0 0 0 1-1v-11" /></svg>
      </button>
    </nav>
  );
}
