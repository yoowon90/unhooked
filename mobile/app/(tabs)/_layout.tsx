import { Tabs } from 'expo-router';
import { useAuth } from '../../context/auth';
import { TouchableOpacity, Text } from 'react-native';

export default function TabsLayout() {
  const { logout } = useAuth();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#000',
        headerRight: () => (
          <TouchableOpacity onPress={logout} style={{ marginRight: 16 }}>
            <Text style={{ color: '#888', fontSize: 14 }}>Log out</Text>
          </TouchableOpacity>
        ),
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Wishlist' }} />
      <Tabs.Screen name="purchased" options={{ title: 'Purchased' }} />
      <Tabs.Screen name="unhooked" options={{ title: 'Unhooked' }} />
    </Tabs>
  );
}
