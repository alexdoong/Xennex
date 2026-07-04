import React, { useEffect, useState } from 'react';

interface Character {
  name: string;
  element: string;
  weapon: string;
  rarity: number;
  portrait: string;
  stats_lvl90: {
    hp: number;
    atk: number;
    def: number;
    crit_rate: number;
    crit_dmg: number;
  };
  build_recommendations: {
    best_echo_set: string;
    best_echo_main: string;
    stat_priority: string;
    cost_4_stat: string;
    cost_3_stat: string;
    cost_1_stat: string;
  };
  best_weapons: string[];
}

const WuWaTab: React.FC = () => {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [selectedChar, setSelectedChar] = useState<Character | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDatabase = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('data/wuwa_characters.json');
      if (res.ok) {
        const data = await res.json();
        setCharacters(data);
      } else {
        setError('Failed to load database. File not found.');
      }
    } catch (err: any) {
      setError(`Error loading database: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDatabase();
  }, []);

  return (
    <div className="tab-content" id="tab-wuwa-db">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ margin: 0 }}>Character Database</h2>
        <button className="btn" onClick={loadDatabase} disabled={loading}>
          {loading ? 'Loading...' : 'Reload DB'}
        </button>
      </div>

      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}

      <div className="character-grid">
        {characters.map((char) => (
          <div key={char.name} className={`char-card rarity-${char.rarity}`} onClick={() => setSelectedChar(char)}>
            <img
              src={char.portrait}
              alt={char.name}
              onError={(e) => {
                e.currentTarget.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iIzMzMyIvPjwvc3ZnPg==';
              }}
            />
            <div className="char-name">{char.name}</div>
          </div>
        ))}
      </div>

      {selectedChar && (
        <div className="modal-overlay" onClick={() => setSelectedChar(null)}>
          <div className="modal-content glass-panel" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={() => setSelectedChar(null)}>&times;</button>
            <div style={{ display: 'flex', gap: '24px', marginBottom: '24px' }}>
              <div style={{ flexShrink: 0 }}>
                <img
                  src={selectedChar.portrait}
                  alt={selectedChar.name}
                  style={{
                    width: '120px',
                    height: '120px',
                    borderRadius: '8px',
                    objectFit: 'cover',
                    border: `2px solid ${selectedChar.rarity === 5 ? '#ffd700' : '#a335ee'}`
                  }}
                  onError={(e) => {
                    e.currentTarget.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iIzMzMyIvPjwvc3ZnPg==';
                  }}
                />
              </div>
              <div>
                <h2 style={{ marginBottom: '8px' }}>{selectedChar.name}</h2>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'grid', gap: '4px' }}>
                  <p><strong>Element:</strong> {selectedChar.element}</p>
                  <p><strong>Weapon:</strong> {selectedChar.weapon}</p>
                  <p><strong>Rarity:</strong> {selectedChar.rarity}★</p>
                </div>
              </div>
            </div>

            <div className="card">
              <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>Lv. 90 Stats</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '13px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>HP</span> <strong>{selectedChar.stats_lvl90.hp}</strong></div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>ATK</span> <strong>{selectedChar.stats_lvl90.atk}</strong></div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>DEF</span> <strong>{selectedChar.stats_lvl90.def}</strong></div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Crit Rate</span> <strong>{selectedChar.stats_lvl90.crit_rate}%</strong></div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Crit DMG</span> <strong>{selectedChar.stats_lvl90.crit_dmg}%</strong></div>
              </div>
            </div>

            <div className="card">
              <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>Recommended Build</h3>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'grid', gap: '6px' }}>
                <p><strong>Best Echo Set:</strong> {selectedChar.build_recommendations.best_echo_set}</p>
                <p><strong>Main Echo:</strong> {selectedChar.build_recommendations.best_echo_main}</p>
                <p><strong>Stat Priority:</strong> {selectedChar.build_recommendations.stat_priority}</p>
                <p><strong>4-Cost:</strong> {selectedChar.build_recommendations.cost_4_stat}</p>
                <p><strong>3-Cost:</strong> {selectedChar.build_recommendations.cost_3_stat}</p>
                <p><strong>1-Cost:</strong> {selectedChar.build_recommendations.cost_1_stat}</p>
              </div>
            </div>

            <div className="card" style={{ marginBottom: 0 }}>
              <h3 style={{ fontSize: '14px', marginBottom: '12px' }}>Top Weapons</h3>
              <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                {selectedChar.best_weapons.map(w => <li key={w}>{w}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WuWaTab;
