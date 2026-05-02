import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, FlatList, StyleSheet, TouchableOpacity,
  RefreshControl, Alert, ActivityIndicator,
} from 'react-native';
import { wishItemsApi, WishItem } from '../../services/api';

export default function UnhookedScreen() {
  const [items, setItems] = useState<WishItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function fetchItems() {
    try {
      const data = await wishItemsApi.list({ status: 'unhooked' });
      setItems(data);
    } catch (e: any) {
      Alert.alert('Error', e.message);
    }
  }

  useEffect(() => {
    fetchItems().finally(() => setLoading(false));
  }, []);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchItems();
    setRefreshing(false);
  }, []);

  async function moveToWishlist(item: WishItem) {
    try {
      await wishItemsApi.setStatus(item.id, 'wishlist');
      setItems(prev => prev.filter(i => i.id !== item.id));
    } catch (e: any) {
      Alert.alert('Error', e.message);
    }
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  const totalSaved = items.reduce((sum, i) => sum + (i.price ?? 0), 0);

  return (
    <FlatList
      data={items}
      keyExtractor={item => String(item.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      contentContainerStyle={items.length === 0 ? styles.center : styles.list}
      ListEmptyComponent={<Text style={styles.empty}>Nothing unhooked yet.</Text>}
      ListHeaderComponent={
        items.length > 0 ? (
          <Text style={styles.saved}>Saved by not buying: ${totalSaved.toFixed(2)}</Text>
        ) : null
      }
      renderItem={({ item }) => (
        <TouchableOpacity style={styles.card} onPress={() => moveToWishlist(item)}>
          <View style={styles.cardHeader}>
            <Text style={styles.brand}>{item.brand}</Text>
            <Text style={styles.date}>
              {item.unhooked_date ? new Date(item.unhooked_date).toLocaleDateString() : ''}
            </Text>
          </View>
          <Text style={styles.name}>{item.name}</Text>
          <View style={styles.cardFooter}>
            <Text style={styles.category}>{item.category}</Text>
            <Text style={styles.price}>${item.price?.toFixed(2)}</Text>
          </View>
          <Text style={styles.hint}>Tap to move back to wishlist</Text>
        </TouchableOpacity>
      )}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 16 },
  empty: { color: '#aaa', fontSize: 16 },
  saved: { fontSize: 15, fontWeight: '600', marginBottom: 12, color: '#333' },
  card: {
    backgroundColor: '#fff', borderRadius: 10, padding: 14,
    marginBottom: 12, shadowColor: '#000',
    shadowOpacity: 0.06, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  brand: { fontSize: 12, color: '#888', textTransform: 'uppercase', fontWeight: '600' },
  date: { fontSize: 12, color: '#aaa' },
  name: { fontSize: 16, fontWeight: '600', marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  category: { fontSize: 13, color: '#999' },
  price: { fontSize: 15, fontWeight: '600' },
  hint: { fontSize: 11, color: '#ccc', marginTop: 2 },
});
