import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, Alert, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { Link } from 'expo-router';
import { useAuth } from '../../context/auth';

export default function SignupScreen() {
  const { signup } = useAuth();
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [password, setPassword] = useState('');
  const [zipcode, setZipcode] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSignup() {
    if (!email || !firstName || !password || !zipcode) {
      Alert.alert('Error', 'All fields are required.');
      return;
    }
    setLoading(true);
    try {
      await signup(email.trim(), firstName.trim(), password, zipcode.trim());
    } catch (e: any) {
      Alert.alert('Sign up failed', e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Create account</Text>

        <TextInput
          style={styles.input} placeholder="First name"
          value={firstName} onChangeText={setFirstName}
        />
        <TextInput
          style={styles.input} placeholder="Email"
          value={email} onChangeText={setEmail}
          autoCapitalize="none" keyboardType="email-address"
        />
        <TextInput
          style={styles.input} placeholder="Password (7+ characters)"
          value={password} onChangeText={setPassword}
          secureTextEntry
        />
        <TextInput
          style={styles.input} placeholder="Zip code"
          value={zipcode} onChangeText={setZipcode}
          keyboardType="number-pad" maxLength={5}
        />

        <TouchableOpacity style={styles.button} onPress={handleSignup} disabled={loading}>
          <Text style={styles.buttonText}>{loading ? 'Creating account…' : 'Sign up'}</Text>
        </TouchableOpacity>

        <Link href="/(auth)/login" style={styles.link}>
          Already have an account? Log in
        </Link>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1, justifyContent: 'center', padding: 24, backgroundColor: '#fff',
  },
  title: {
    fontSize: 28, fontWeight: '700', marginBottom: 28,
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
