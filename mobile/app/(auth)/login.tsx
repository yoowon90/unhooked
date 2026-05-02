import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, Alert, KeyboardAvoidingView, Platform,
} from 'react-native';
import { Link } from 'expo-router';
import { useAuth } from '../../context/auth';

export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    if (!email || !password) {
      Alert.alert('Error', 'Please enter email and password.');
      return;
    }
    setLoading(true);
    try {
      await login(email.trim(), password);
    } catch (e: any) {
      Alert.alert('Login failed', e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Text style={styles.title}>Unhooked</Text>
      <Text style={styles.subtitle}>Track what you want. Skip what you don't.</Text>

      <TextInput
        style={styles.input}
        placeholder="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
      />

      <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={loading}>
        <Text style={styles.buttonText}>{loading ? 'Logging in…' : 'Log in'}</Text>
      </TouchableOpacity>

      <Link href="/(auth)/signup" style={styles.link}>
        Don't have an account? Sign up
      </Link>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1, justifyContent: 'center', padding: 24, backgroundColor: '#fff',
  },
  title: {
    fontSize: 32, fontWeight: '700', textAlign: 'center', marginBottom: 6,
  },
  subtitle: {
    fontSize: 14, color: '#888', textAlign: 'center', marginBottom: 36,
  },
  input: {
    borderWidth: 1, borderColor: '#ddd', borderRadius: 8,
    padding: 12, fontSize: 16, marginBottom: 12,
  },
  button: {
    backgroundColor: '#000', borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 4,
  },
  buttonText: {
    color: '#fff', fontSize: 16, fontWeight: '600',
  },
  link: {
    marginTop: 20, textAlign: 'center', color: '#555', fontSize: 14,
  },
});
