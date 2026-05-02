import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, FlatList, StyleSheet, TouchableOpacity,
  RefreshControl, Alert, ActivityIndicator,
} from 'react-native';
import { wishItemsApi, WishItem } from '../../services/api';

export default function WishlistScreen() {
  const [items, setItems] = useState<WishItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function fetchItems() {
    try {
      const data = await wishItemsApi.list({ status: 'wishlist' });
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

  async function markPurchased(item: WishItem) {
    try {
      await wishItemsApi.setStatus(item.id, 'purchased');
      setItems(prev => prev.filter(i => i.id !== item.id));
    } catch (e: any) {
      Alert.alert('Error', e.message);
    }
  }

  async function markUnhooked(item: WishItem) {
    try {
      await wishItemsApi.setStatus(item.id, 'unhooked');
      setItems(prev => prev.filter(i => i.id !== item.id));
    } catch (e: any) {
      Alert.alert('Error', e.message);
    }
  }

  function openActions(item: WishItem) {
    Alert.alert(item.name, `$${item.price.toFixed(2)}`, [
      { text: 'Mark purchased', onPress: () => markPurchased(item) },
      { text: 'Unhook (skip)', onPress: () => markUnhooked(item) },
      { text: 'Cancel', style: 'cancel' },
    ]);
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <FlatList
      data={items}
      keyExtractor={item => String(item.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      contentContainerStyle={items.length === 0 ? styles.center : styles.list}
      ListEmptyComponent={<Text style={styles.empty}>Your wishlist is empty.</Text>}
      renderItem={({ item }) => (
        <TouchableOpacity style={styles.card} onPress={() => openActions(item)}>
          <View style={styles.cardHeader}>
            <Text style={styles.brand}>{item.brand}</Text>
            {item.tag ? <Text style={styles.tag}>#{item.tag}</Text> : null}
          </View>
          <Text style={styles.name}>{item.name}</Text>
          <View style={styles.cardFooter}>
            <Text style={styles.category}>{item.category}</Text>
            <Text style={styles.price}>${item.price.toFixed(2)}</Text>
          </View>
        </TouchableOpacity>
      )}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 16 },
  empty: { color: '#aaa', fontSize: 16 },
  card: {
    backgroundColor: '#fff', borderRadius: 10, padding: 14,
    marginBottom: 12, shadowColor: '#000',
    shadowOpacity: 0.06, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  brand: { fontSize: 12, color: '#888', textTransform: 'uppercase', fontWeight: '600' },
  tag: { fontSize: 12, color: '#aaa' },
  name: { fontSize: 16, fontWeight: '600', marginBottom: 8 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between' },
  category: { fontSize: 13, color: '#999' },
  price: { fontSize: 15, fontWeight: '600' },
});
