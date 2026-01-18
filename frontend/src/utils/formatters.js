// Formatar data de YYYY-MM-DD para DD/MM/YYYY
export const formatDateBR = (dateString) => {
  if (!dateString) return '';
  const [year, month, day] = dateString.split('-');
  return `${day}/${month}/${year}`;
};

// Formatar data de DD/MM/YYYY para YYYY-MM-DD
export const formatDateISO = (dateString) => {
  if (!dateString) return '';
  const [day, month, year] = dateString.split('/');
  return `${year}-${month}-${day}`;
};

// Formatar moeda BRL
export const formatCurrency = (value) => {
  if (value === null || value === undefined) return 'R$ 0,00';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
};

// Formatar CPF
export const formatCPF = (value) => {
  if (!value) return '';
  return value
    .replace(/\D/g, '')
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d{1,2})/, '$1-$2')
    .replace(/(-\d{2})\d+?$/, '$1');
};

// Remover máscara de CPF
export const unformatCPF = (value) => {
  if (!value) return '';
  return value.replace(/\D/g, '');
};

// Formatar número para input de moeda
export const formatCurrencyInput = (value) => {
  if (!value) return '';
  const numericValue = parseFloat(value);
  if (isNaN(numericValue)) return '';
  return numericValue.toFixed(2);
};
